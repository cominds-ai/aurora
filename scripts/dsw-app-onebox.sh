#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${AURORA_RUNTIME_ROOT:-/root/aurora-runtime}"
UI_ROOT="${AURORA_UI_RUNTIME_ROOT:-/root/aurora-ui-runtime}"
UI_STANDALONE_ROOT="${AURORA_UI_STANDALONE_ROOT:-/root/aurora-ui-standalone}"
STATE_ROOT="${AURORA_STATE_ROOT:-$(cd "$SOURCE_ROOT/.." && pwd)/aurora-state}"
SECRETS_FILE="${AURORA_SECRETS_FILE:-$(cd "$SOURCE_ROOT/.." && pwd)/.aurora-secrets.env}"
LOG_DIR="$STATE_ROOT/logs"
RUN_DIR="$STATE_ROOT/run"
POSTGRES_DATA="$STATE_ROOT/postgres"
REDIS_DATA="$STATE_ROOT/redis"
REDIS_CONF="$REDIS_DATA/redis.conf"
ENV_FILE="$SOURCE_ROOT/.env"

POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-3000}"
DEFAULT_DB_NAME="${POSTGRES_DB:-aurora}"

: "${NEXT_PUBLIC_API_BASE_URL:?NEXT_PUBLIC_API_BASE_URL is required, e.g. http://<api-service-host>:8000/api}"

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
export DEBIAN_FRONTEND=noninteractive
export UV_CACHE_DIR="$APP_ROOT/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$APP_ROOT/.uv-python"

log() {
  printf '[aurora-dsw] %s\n' "$*"
}

safe_remove_path() {
  local path="$1"

  if [ ! -e "$path" ]; then
    return
  fi

  if rm -rf "$path" 2>/dev/null; then
    return
  fi

  local backup="${path}.bak.$(date +%s)"
  log "failed to remove $path directly, moving it aside: $backup"
  mv "$path" "$backup"
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "missing command: $cmd"
    exit 1
  fi
}

ensure_port_free() {
  local port="$1"
  local label="$2"
  local pids

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return
  fi

  for pid in $pids; do
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    log "stopping stale $label listener on port $port (pid=$pid)"
    log "command: ${cmd:-unknown}"
    kill "$pid" 2>/dev/null || true
  done

  sleep 1

  if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    log "force stopping remaining listener on port $port"
    lsof -tiTCP:"$port" -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

stop_pid_file() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local retries="${3:-60}"

  for _ in $(seq 1 "$retries"); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      log "$label is ready: $url"
      return 0
    fi
    sleep 1
  done

  log "$label did not become ready: $url"
  return 1
}

wait_for_tcp() {
  local host="$1"
  local port="$2"
  local label="$3"
  local retries="${4:-60}"

  for _ in $(seq 1 "$retries"); do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      log "$label is ready on ${host}:${port}"
      return 0
    fi
    sleep 1
  done

  log "$label did not become ready on ${host}:${port}"
  return 1
}

ensure_apt_packages() {
  log "installing system packages..."
  $SUDO apt-get update
  $SUDO apt-get install -y \
    git curl wget ca-certificates gnupg build-essential software-properties-common \
    libpq-dev postgresql postgresql-contrib redis-server netcat-openbsd rsync
}

ensure_node() {
  if command -v node >/dev/null 2>&1 && [ "$(node -v 2>/dev/null || true)" = "v22.14.0" ]; then
    log "node already installed: $(node -v)"
    return
  fi

  log "installing node v22.14.0..."
  local arch node_arch
  arch="$(dpkg --print-architecture)"
  case "$arch" in
    amd64) node_arch="x64" ;;
    arm64) node_arch="arm64" ;;
    *) log "unsupported architecture: $arch"; exit 1 ;;
  esac

  curl -fsSL "https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz
  $SUDO tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
  rm -f /tmp/node.tar.xz
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    log "uv already installed: $(uv --version)"
    return
  fi

  log "installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
}

resolve_postgres_bin_dir() {
  find /usr/lib/postgresql -path '*/bin/initdb' | sort -V | tail -n 1 | xargs dirname
}

ensure_postgres_cluster() {
  local pg_bin_dir
  pg_bin_dir="$(resolve_postgres_bin_dir)"
  if [ -z "$pg_bin_dir" ]; then
    log "postgres initdb not found"
    exit 1
  fi

  $SUDO install -d -m 700 -o postgres -g postgres "$POSTGRES_DATA"

  if [ ! -f "$POSTGRES_DATA/PG_VERSION" ]; then
    log "initializing postgres cluster..."
    $SUDO su postgres -s /bin/bash -c "\"$pg_bin_dir/initdb\" -D \"$POSTGRES_DATA\" --username=postgres --auth=trust --auth-host=trust"
  fi

  if ! $SUDO su postgres -s /bin/bash -c "\"$pg_bin_dir/pg_ctl\" -D \"$POSTGRES_DATA\" status" >/dev/null 2>&1; then
    log "starting postgres..."
    $SUDO su postgres -s /bin/bash -c "\"$pg_bin_dir/pg_ctl\" -D \"$POSTGRES_DATA\" -l \"$POSTGRES_DATA/server.log\" -o \"-h 127.0.0.1 -p $POSTGRES_PORT\" start"
  fi

  wait_for_tcp 127.0.0.1 "$POSTGRES_PORT" "postgres"

  if ! $SUDO su postgres -s /bin/bash -c "psql -h 127.0.0.1 -p $POSTGRES_PORT -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='${DEFAULT_DB_NAME}'\"" | grep -q 1; then
    log "creating database: $DEFAULT_DB_NAME"
    $SUDO su postgres -s /bin/bash -c "createdb -h 127.0.0.1 -p $POSTGRES_PORT ${DEFAULT_DB_NAME}"
  fi
}

ensure_redis() {
  mkdir -p "$REDIS_DATA"

  cat > "$REDIS_CONF" <<EOF
bind 127.0.0.1
port ${REDIS_PORT}
dir ${REDIS_DATA}
appendonly yes
daemonize yes
pidfile ${RUN_DIR}/redis.pid
logfile ${REDIS_DATA}/redis.log
save 60 1000
EOF

  if [ -f "${RUN_DIR}/redis.pid" ] && kill -0 "$(cat "${RUN_DIR}/redis.pid")" 2>/dev/null; then
    log "redis already running"
  else
    log "starting redis..."
    redis-server "$REDIS_CONF"
  fi

  wait_for_tcp 127.0.0.1 "$REDIS_PORT" "redis"
}

ensure_env_file() {
  if [ -f "$ENV_FILE" ]; then
    log ".env already exists, keeping current values"
    return
  fi

  local jwt_secret password_salt
  jwt_secret="$(openssl rand -hex 32)"
  password_salt="$(openssl rand -hex 32)"

  cat > "$ENV_FILE" <<EOF
ENV=production
LOG_LEVEL=INFO

POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_DB=${DEFAULT_DB_NAME}
SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://postgres@127.0.0.1:${POSTGRES_PORT}/${DEFAULT_DB_NAME}

REDIS_HOST=127.0.0.1
REDIS_PORT=${REDIS_PORT}
REDIS_DB=0
REDIS_PASSWORD=

AUTH_JWT_SECRET=${jwt_secret}
AUTH_PASSWORD_SALT=${password_salt}
DEFAULT_LOGIN_PASSWORD=123456

SANDBOX_MODE=registry
SANDBOX_BINDING_TTL_HOURS=72
SANDBOX_REGISTRY_JSON=[]

NGINX_PORT=8088
EOF

  log "generated .env at $ENV_FILE"
}

sync_source_to_runtime() {
  log "syncing source to local runtime directory..."
  mkdir -p "$APP_ROOT"
  rsync -a --delete \
    --exclude '.git/' \
    --exclude '.DS_Store' \
    --exclude '.uv-cache/' \
    --exclude '.uv-python/' \
    --exclude 'aurora-state/' \
    --exclude 'aurora-sandbox-state/' \
    --exclude 'api/.venv/' \
    --exclude 'sandbox/.venv/' \
    --exclude 'ui/node_modules/' \
    --exclude 'ui/.next/' \
    --exclude 'ui/package-lock.json' \
    "$SOURCE_ROOT/" "$APP_ROOT/"

  log "syncing ui source to standalone runtime directory..."
  mkdir -p "$UI_ROOT"
  rsync -a --delete \
    --exclude 'node_modules/' \
    --exclude '.next/' \
    --exclude 'package-lock.json' \
    "$SOURCE_ROOT/ui/" "$UI_ROOT/"
}

start_api() {
  stop_pid_file "$RUN_DIR/api.pid"
  ensure_port_free "$API_PORT" "api"
  : >"$LOG_DIR/api.log"

  log "syncing api dependencies..."
  (
    cd "$APP_ROOT"
    uv sync --package api --python 3.13.9
  )

  log "running alembic migrations..."
  (
    cd "$APP_ROOT"
    PYTHONPATH="$APP_ROOT/api" uv run --package api --python 3.13.9 alembic -c "$APP_ROOT/api/alembic.ini" upgrade head
  )

  log "starting api..."
  (
    cd "$APP_ROOT"
    nohup env \
      PYTHONPATH="$APP_ROOT/api" \
      PATH="$HOME/.local/bin:/usr/local/bin:$PATH" \
      SKIP_STARTUP_MIGRATIONS=1 \
      uv run --package api --python 3.13.9 bash ./api/run.sh \
      >"$LOG_DIR/api.log" 2>&1 &
    echo $! >"$RUN_DIR/api.pid"
  )

  if ! wait_for_http "http://127.0.0.1:${API_PORT}/api/status" "api" 60; then
    log "api failed to start, recent log:"
    tail -n 80 "$LOG_DIR/api.log" || true
    exit 1
  fi
}

start_ui() {
  local lightning_native="$UI_ROOT/node_modules/lightningcss-linux-x64-gnu/lightningcss.linux-x64-gnu.node"
  local tailwind_native="$UI_ROOT/node_modules/@tailwindcss/oxide-linux-x64-gnu/tailwindcss-oxide.linux-x64-gnu.node"
  local npm_userconfig="$RUN_DIR/npmrc.empty"
  local npm_home="${HOME:-/root}"
  local npm_lang="${LANG:-C.UTF-8}"
  local npm_term="${TERM:-dumb}"

  stop_pid_file "$RUN_DIR/ui.pid"
  ensure_port_free "$UI_PORT" "ui"
  : >"$LOG_DIR/ui-build.log"
  : >"$LOG_DIR/ui.log"
  : >"$npm_userconfig"

  log "cleaning previous ui install artifacts..."
  safe_remove_path "$UI_ROOT/node_modules"
  safe_remove_path "$UI_ROOT/.next"
  safe_remove_path "$UI_ROOT/package-lock.json"
  safe_remove_path "$UI_STANDALONE_ROOT"

  log "installing ui dependencies in standalone mode..."
  (
    cd "$UI_ROOT"
    env -i \
      HOME="$npm_home" \
      PATH="$PATH" \
      TERM="$npm_term" \
      LANG="$npm_lang" \
      LC_ALL="$npm_lang" \
      NPM_CONFIG_USERCONFIG="$npm_userconfig" \
      npm_config_workspaces=false \
      npm install --include=optional --package-lock=false --workspaces=false
  )

  log "ensuring ui linux native dependencies..."
  (
    cd "$UI_ROOT"
    env -i \
      HOME="$npm_home" \
      PATH="$PATH" \
      TERM="$npm_term" \
      LANG="$npm_lang" \
      LC_ALL="$npm_lang" \
      NPM_CONFIG_USERCONFIG="$npm_userconfig" \
      npm_config_workspaces=false \
      npm install --package-lock=false --no-save \
        lightningcss-linux-x64-gnu@1.30.2 \
        @tailwindcss/oxide-linux-x64-gnu@4.1.18
  )

  if [ ! -f "$lightning_native" ] || [ ! -f "$tailwind_native" ]; then
    log "ui linux native dependencies are missing after install"
    log "expected: $lightning_native"
    log "expected: $tailwind_native"
    exit 1
  fi

  log "building ui with webpack..."
  if ! (
    cd "$UI_ROOT"
    NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" npm run build -- --webpack >"$LOG_DIR/ui-build.log" 2>&1
  ); then
    log "ui build failed, recent build log:"
    tail -n 120 "$LOG_DIR/ui-build.log" || true
    exit 1
  fi

  log "preparing standalone ui runtime..."
  mkdir -p "$UI_STANDALONE_ROOT"
  cp -R "$UI_ROOT/.next/standalone/." "$UI_STANDALONE_ROOT/"
  mkdir -p "$UI_STANDALONE_ROOT/.next"
  cp -R "$UI_ROOT/.next/static" "$UI_STANDALONE_ROOT/.next/static"
  cp -R "$UI_ROOT/public" "$UI_STANDALONE_ROOT/public"

  log "starting ui..."
  (
    cd "$UI_STANDALONE_ROOT"
    nohup env \
      NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" \
      PORT="$UI_PORT" \
      HOSTNAME="0.0.0.0" \
      node server.js \
      >"$LOG_DIR/ui.log" 2>&1 &
    echo $! >"$RUN_DIR/ui.pid"
  )

  if ! wait_for_http "http://127.0.0.1:${UI_PORT}" "ui" 60; then
    log "ui failed to start, recent build log:"
    tail -n 80 "$LOG_DIR/ui-build.log" || true
    log "ui failed to start, recent runtime log:"
    tail -n 80 "$LOG_DIR/ui.log" || true
    exit 1
  fi
}

main() {
  require_command curl
  require_command openssl

  mkdir -p "$LOG_DIR" "$RUN_DIR"

  ensure_apt_packages
  ensure_node
  ensure_uv
  require_command uv
  require_command node
  require_command npm
  require_command redis-server
  require_command rsync

  ensure_postgres_cluster
  ensure_redis
  ensure_env_file
  sync_source_to_runtime

  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  if [ -f "$SECRETS_FILE" ]; then
    log "loading secrets file: $SECRETS_FILE"
    # shellcheck disable=SC1090
    source "$SECRETS_FILE"
  else
    log "secrets file not found, continuing without it: $SECRETS_FILE"
  fi
  set +a

  start_api
  start_ui

  cat <<EOF
[aurora-dsw] one-box app stack started
[aurora-dsw] app root: $APP_ROOT
[aurora-dsw] ui root: $UI_ROOT
[aurora-dsw] ui standalone root: $UI_STANDALONE_ROOT
[aurora-dsw] state root: $STATE_ROOT
[aurora-dsw] secrets file: $SECRETS_FILE
[aurora-dsw] ui url: http://127.0.0.1:${UI_PORT}
[aurora-dsw] api url: http://127.0.0.1:${API_PORT}/api
[aurora-dsw] api public base: ${NEXT_PUBLIC_API_BASE_URL}
[aurora-dsw] postgres data: $POSTGRES_DATA
[aurora-dsw] redis data: $REDIS_DATA
[aurora-dsw] api log: $LOG_DIR/api.log
[aurora-dsw] ui build log: $LOG_DIR/ui-build.log
[aurora-dsw] ui log: $LOG_DIR/ui.log
[aurora-dsw] postgres log: $POSTGRES_DATA/server.log
[aurora-dsw] redis log: $REDIS_DATA/redis.log
EOF
}

main "$@"
