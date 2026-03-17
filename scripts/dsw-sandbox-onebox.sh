#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX_ROOT="$ROOT_DIR/sandbox"
STATE_ROOT="${AURORA_SANDBOX_STATE_ROOT:-$(cd "$ROOT_DIR/.." && pwd)/aurora-sandbox-state}"
LOG_DIR="$STATE_ROOT/logs"
RUN_DIR="$STATE_ROOT/run"
ENV_FILE="$SANDBOX_ROOT/.env"

SANDBOX_API_PORT="${SANDBOX_API_PORT:-8080}"
SANDBOX_CDP_PORT="${SANDBOX_CDP_PORT:-9222}"
SANDBOX_VNC_PORT="${SANDBOX_VNC_PORT:-5900}"
SANDBOX_VNC_WS_PORT="${SANDBOX_VNC_WS_PORT:-5901}"
SANDBOX_SCREEN_WIDTH="${SANDBOX_SCREEN_WIDTH:-1280}"
SANDBOX_SCREEN_HEIGHT="${SANDBOX_SCREEN_HEIGHT:-1080}"
SANDBOX_TIMEOUT_MINUTES="${SANDBOX_TIMEOUT_MINUTES:-}"
SANDBOX_LOG_LEVEL="${SANDBOX_LOG_LEVEL:-INFO}"
SANDBOX_CHROME_ARGS="${SANDBOX_CHROME_ARGS:-}"
SANDBOX_UVI_ARGS="${SANDBOX_UVI_ARGS:-}"

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
export DEBIAN_FRONTEND=noninteractive

log() {
  printf '[aurora-sandbox-dsw] %s\n' "$*"
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
  local retries="${3:-90}"

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

ensure_apt_packages() {
  log "installing system packages..."
  $SUDO apt-get update
  $SUDO apt-get install -y \
    curl wget ca-certificates gnupg software-properties-common \
    supervisor xterm socat xvfb x11vnc websockify \
    fonts-noto-cjk fonts-noto-color-emoji language-pack-zh-hans locales \
    netcat-openbsd lsof
}

ensure_locale() {
  if ! locale -a 2>/dev/null | grep -qi '^zh_CN\.utf8$'; then
    log "generating locale zh_CN.UTF-8..."
    $SUDO locale-gen zh_CN.UTF-8
  fi
}

ensure_chromium() {
  if command -v chromium >/dev/null 2>&1; then
    log "chromium already installed: $(chromium --version | head -n 1)"
    return
  fi

  log "installing chromium..."
  /usr/bin/python3.10 /usr/bin/add-apt-repository ppa:xtradeb/apps -y
  $SUDO apt-get update
  $SUDO apt-get install -y chromium --no-install-recommends
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

ensure_ubuntu_user() {
  if id -u ubuntu >/dev/null 2>&1; then
    return
  fi

  log "creating ubuntu user for sandbox runtime..."
  $SUDO useradd -m -d /home/ubuntu -s /bin/bash ubuntu
}

ensure_env_file() {
  cat > "$ENV_FILE" <<EOF
LOG_LEVEL=${SANDBOX_LOG_LEVEL}
SERVER_TIMEOUT_MINUTES=${SANDBOX_TIMEOUT_MINUTES}
SCREEN_WIDTH=${SANDBOX_SCREEN_WIDTH}
SCREEN_HEIGHT=${SANDBOX_SCREEN_HEIGHT}
EOF
  log "generated sandbox env at $ENV_FILE"
}

start_sandbox() {
  stop_pid_file "$RUN_DIR/supervisord.pid"
  ensure_port_free "$SANDBOX_API_PORT" "sandbox-api"
  ensure_port_free "$SANDBOX_CDP_PORT" "sandbox-cdp"
  ensure_port_free "$SANDBOX_VNC_PORT" "sandbox-vnc"
  ensure_port_free "$SANDBOX_VNC_WS_PORT" "sandbox-vnc-ws"
  pkill -f "supervisord.*sandbox/supervisord.conf" 2>/dev/null || true
  pkill -f "uvicorn app.main:app --host 0.0.0.0 --port ${SANDBOX_API_PORT}" 2>/dev/null || true
  pkill -f "socat TCP-LISTEN:${SANDBOX_CDP_PORT}" 2>/dev/null || true
  pkill -f "x11vnc -display :1" 2>/dev/null || true
  pkill -f "websockify 0.0.0.0:${SANDBOX_VNC_WS_PORT}" 2>/dev/null || true
  pkill -f "Xvfb :1 -screen 0 ${SANDBOX_SCREEN_WIDTH}x${SANDBOX_SCREEN_HEIGHT}x24" 2>/dev/null || true
  pkill -f "/tmp/chromium-profile" 2>/dev/null || true
  sleep 1

  : >"$LOG_DIR/sandbox.log"

  log "syncing sandbox dependencies..."
  (
    cd "$SANDBOX_ROOT"
    uv sync --project "$SANDBOX_ROOT"
  )

  log "starting sandbox supervisor..."
  (
    cd "$SANDBOX_ROOT"
    nohup env \
      PATH="$HOME/.local/bin:/usr/local/bin:$PATH" \
      ENV=production \
      LOG_LEVEL="$SANDBOX_LOG_LEVEL" \
      SERVER_TIMEOUT_MINUTES="$SANDBOX_TIMEOUT_MINUTES" \
      SANDBOX_ROOT="$SANDBOX_ROOT" \
      LANG=zh_CN.UTF-8 \
      LANGUAGE=zh_CN:zh \
      LC_ALL=zh_CN.UTF-8 \
      CHROME_ARGS="$SANDBOX_CHROME_ARGS" \
      UVI_ARGS="$SANDBOX_UVI_ARGS" \
      /usr/bin/supervisord -n -c "$SANDBOX_ROOT/supervisord.conf" \
      >"$LOG_DIR/sandbox.log" 2>&1 &
    echo $! >"$RUN_DIR/supervisord.pid"
  )

  if ! wait_for_http "http://127.0.0.1:${SANDBOX_API_PORT}/api/supervisor/status" "sandbox" 90; then
    log "sandbox failed to start, recent log:"
    tail -n 120 "$LOG_DIR/sandbox.log" || true
    exit 1
  fi
}

main() {
  require_command curl

  mkdir -p "$LOG_DIR" "$RUN_DIR"

  ensure_apt_packages
  ensure_locale
  ensure_chromium
  ensure_node
  ensure_uv
  ensure_ubuntu_user
  require_command uv
  require_command node
  require_command npm
  require_command chromium
  require_command /usr/bin/supervisord

  ensure_env_file
  start_sandbox

  cat <<EOF
[aurora-sandbox-dsw] sandbox started
[aurora-sandbox-dsw] sandbox root: $SANDBOX_ROOT
[aurora-sandbox-dsw] state root: $STATE_ROOT
[aurora-sandbox-dsw] api url: http://127.0.0.1:${SANDBOX_API_PORT}
[aurora-sandbox-dsw] cdp url: http://127.0.0.1:${SANDBOX_CDP_PORT}
[aurora-sandbox-dsw] vnc ws url: ws://127.0.0.1:${SANDBOX_VNC_WS_PORT}
[aurora-sandbox-dsw] runtime log: $LOG_DIR/sandbox.log
[aurora-sandbox-dsw] env file: $ENV_FILE
EOF
}

main "$@"
