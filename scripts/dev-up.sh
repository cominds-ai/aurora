#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs/dev"
SANDBOX_HASH_FILE="$LOG_DIR/sandbox-image.hash"
SANDBOX_META_FILE="$LOG_DIR/sandbox-image.meta"
FOLLOW_PIDS=()
SHUTDOWN_DONE=0
FOLLOW_LOGS=1
CLEANUP_ON_EXIT=1
COMPOSE_PROJECT="aurora-local"
COMPOSE_ENV_FILE=".env.example"
SCRIPT_TTY=""
HOST_DOCKER_PLATFORM=""
export AURORA_SANDBOX_IMAGE="aurora-sandbox-local"
export AURORA_REDIS_VOLUME="aurora_local_redis_data"
export AURORA_POSTGRES_VOLUME="aurora_local_postgres_data"
export AURORA_NETWORK_NAME="aurora-local-network"

mkdir -p "$LOG_DIR"

if [ -t 1 ]; then
  SCRIPT_TTY="$(tty 2>/dev/null || true)"
fi

if [ -n "$SCRIPT_TTY" ] && [ -w "$SCRIPT_TTY" ]; then
  exec 3>"$SCRIPT_TTY"
else
  exec 3>&1
fi

case "$(uname -m)" in
  arm64|aarch64)
    HOST_DOCKER_PLATFORM="linux/arm64"
    ;;
  x86_64|amd64)
    HOST_DOCKER_PLATFORM="linux/amd64"
    ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --follow-logs|-f)
      FOLLOW_LOGS=1
      ;;
    --no-follow-logs|-d)
      FOLLOW_LOGS=0
      ;;
    --help|-h)
      cat <<'EOF'
Usage: ./scripts/dev-up.sh [--follow-logs|--no-follow-logs]

Options:
  --follow-logs, -f     Keep streaming API/UI/infra logs in the foreground.
  --no-follow-logs, -d  Start services and exit after startup.
  --help, -h            Show this help.
EOF
      exit 0
      ;;
    *)
      echo "[aurora] unknown argument: $1"
      exit 1
      ;;
  esac
  shift
done

run_docker() {
  if [ -n "$HOST_DOCKER_PLATFORM" ]; then
    DOCKER_DEFAULT_PLATFORM="$HOST_DOCKER_PLATFORM" "$@"
    return
  fi
  "$@"
}

cleanup_followers() {
  for pid in "${FOLLOW_PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

kill_process_tree() {
  local pid="$1"
  local children

  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  if [ -n "$children" ]; then
    for child in $children; do
      kill_process_tree "$child"
    done
  fi

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
}

stop_pid_file() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    kill_process_tree "$pid"
    rm -f "$pid_file"
  fi
}

shutdown_all() {
  if [ "$CLEANUP_ON_EXIT" -eq 0 ] || [ "$SHUTDOWN_DONE" -eq 1 ]; then
    return
  fi
  SHUTDOWN_DONE=1

  echo
  echo "[aurora] stopping local services..."
  cleanup_followers
  stop_pid_file "$LOG_DIR/api.pid"
  stop_pid_file "$LOG_DIR/ui.pid"

  (
    cd "$ROOT_DIR"
    run_docker docker compose -p "$COMPOSE_PROJECT" --env-file "$COMPOSE_ENV_FILE" down >/dev/null 2>&1 || true
  )

  echo "[aurora] all local services stopped"
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
    echo "[aurora] stopping stale $label listener on port $port (pid=$pid)"
    echo "[aurora] command: ${cmd:-unknown}"
    kill "$pid" 2>/dev/null || true
  done

  sleep 1

  if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[aurora] force stopping remaining listener on port $port"
    lsof -tiTCP:"$port" -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    sleep 1
  fi

  if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[aurora] failed to free port $port"
    exit 1
  fi
}

wait_for_port() {
  local host="$1"
  local port="$2"
  local label="$3"
  local retries="${4:-60}"

  for _ in $(seq 1 "$retries"); do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      echo "[aurora] $label is ready on ${host}:${port}"
      return 0
    fi
    sleep 1
  done

  echo "[aurora] $label did not become ready on ${host}:${port}"
  return 1
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local retries="${3:-60}"

  for _ in $(seq 1 "$retries"); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "[aurora] $label is ready: $url"
      return 0
    fi
    sleep 1
  done

  echo "[aurora] $label did not become ready: $url"
  return 1
}

compute_sandbox_hash() {
  (
    find "$ROOT_DIR/sandbox" -type f | LC_ALL=C sort | while IFS= read -r file; do
      shasum "$file"
    done | shasum | awk '{print $1}'
  )
}

ensure_sandbox_image() {
  local current_hash
  local previous_hash=""
  local current_meta
  local previous_meta=""

  current_hash="$(compute_sandbox_hash)"
  current_meta="${current_hash}|${HOST_DOCKER_PLATFORM}"
  if [ -f "$SANDBOX_HASH_FILE" ]; then
    previous_hash="$(cat "$SANDBOX_HASH_FILE")"
  fi
  if [ -f "$SANDBOX_META_FILE" ]; then
    previous_meta="$(cat "$SANDBOX_META_FILE")"
  fi

  if ! run_docker docker image inspect "$AURORA_SANDBOX_IMAGE" >/dev/null 2>&1 || [ "$current_hash" != "$previous_hash" ] || [ "$current_meta" != "$previous_meta" ]; then
    echo "[aurora] rebuilding sandbox image..."
    run_docker docker compose -p "$COMPOSE_PROJECT" --env-file "$COMPOSE_ENV_FILE" build aurora-sandbox
    printf '%s' "$current_hash" >"$SANDBOX_HASH_FILE"
    printf '%s' "$current_meta" >"$SANDBOX_META_FILE"
  fi
}

start_api() {
  : >"$LOG_DIR/api.log"
  echo "[aurora] starting api on http://localhost:8000 ..."
  ensure_port_free 8000 "api"
  (
    cd "$ROOT_DIR/api"
    nohup env \
      ENV=development \
      UV_CACHE_DIR="/tmp/aurora-uv-cache" \
      uv run --project "$ROOT_DIR/api" \
      uvicorn app.main:app --app-dir "$ROOT_DIR/api" --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 0 \
      </dev/null >"$LOG_DIR/api.log" 2>&1 &
    echo $! >"$LOG_DIR/api.pid"
  )
}

start_ui() {
  : >"$LOG_DIR/ui.log"
  echo "[aurora] starting ui on http://localhost:3000 ..."
  (
    cd "$ROOT_DIR/ui"
    nohup env \
      NEXT_PUBLIC_API_BASE_URL="http://localhost:8000/api" \
      npm run dev -- --hostname 0.0.0.0 --port 3000 \
      </dev/null >"$LOG_DIR/ui.log" 2>&1 &
    echo $! >"$LOG_DIR/ui.pid"
  )
}

follow_file() {
  local label="$1"
  local file="$2"
  touch "$file"
  (
    tail -n 40 -F "$file" 2>/dev/null | while IFS= read -r line; do
      printf '[%s] %s\n' "$label" "$line" >&3
    done
  ) &
  FOLLOW_PIDS+=("$!")
}

follow_infra_logs() {
  (
    run_docker docker compose -p "$COMPOSE_PROJECT" --env-file "$COMPOSE_ENV_FILE" logs -f --tail=20 aurora-postgres aurora-redis aurora-sandbox 2>/dev/null | while IFS= read -r line; do
      printf '[infra] %s\n' "$line" >&3
    done
  ) &
  FOLLOW_PIDS+=("$!")
}

trap 'shutdown_all' EXIT INT TERM

if ! command -v uv >/dev/null 2>&1; then
  echo "[aurora] uv is required"
  exit 1
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "[aurora] node and npm are required"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[aurora] docker is required"
  exit 1
fi

echo "[aurora] expected python version: 3.13.9"
echo "[aurora] expected node version: 22.14.0"
echo "[aurora] local env file: .env.example"
if [ -n "$HOST_DOCKER_PLATFORM" ]; then
  echo "[aurora] docker platform: $HOST_DOCKER_PLATFORM"
fi
echo "[aurora] starting local infrastructure with docker compose..."

cd "$ROOT_DIR"
stop_pid_file "$LOG_DIR/api.pid"
stop_pid_file "$LOG_DIR/ui.pid"
ensure_port_free 8000 "api"
ensure_port_free 3000 "ui"

ensure_sandbox_image

run_docker docker compose -p "$COMPOSE_PROJECT" --env-file "$COMPOSE_ENV_FILE" up -d aurora-postgres aurora-redis aurora-sandbox

wait_for_port 127.0.0.1 5432 "postgres"
wait_for_port 127.0.0.1 6379 "redis"
if ! wait_for_http "http://127.0.0.1:8080/api/supervisor/status" "sandbox" 60; then
  echo "[aurora] sandbox failed to start, check: docker compose -p $COMPOSE_PROJECT --env-file $COMPOSE_ENV_FILE logs aurora-sandbox"
  exit 1
fi

echo "[aurora] syncing api dependencies with uv..."
UV_CACHE_DIR="/tmp/aurora-uv-cache" uv sync --project "$ROOT_DIR/api"

if [ ! -d "$ROOT_DIR/ui/node_modules" ]; then
  echo "[aurora] installing ui dependencies..."
  (cd "$ROOT_DIR/ui" && npm install)
fi

if [ -f "$LOG_DIR/api.pid" ] && kill -0 "$(cat "$LOG_DIR/api.pid")" 2>/dev/null; then
  echo "[aurora] api already running, skipping"
else
  start_api
  if ! wait_for_http "http://127.0.0.1:8000/api/status" "api" 30; then
    if grep -q "Address already in use" "$LOG_DIR/api.log" 2>/dev/null; then
      echo "[aurora] api port conflict detected, retrying once..."
      stop_pid_file "$LOG_DIR/api.pid"
      ensure_port_free 8000 "api"
      start_api
      wait_for_http "http://127.0.0.1:8000/api/status" "api" 30 || true
    fi
  fi
fi

if [ -f "$LOG_DIR/ui.pid" ] && kill -0 "$(cat "$LOG_DIR/ui.pid")" 2>/dev/null; then
  echo "[aurora] ui already running, skipping"
else
  start_ui
  wait_for_http "http://127.0.0.1:3000" "ui" 30 || true
fi

echo "[aurora] ui: http://localhost:3000"
echo "[aurora] api: http://localhost:8000/api"
echo "[aurora] api docs: http://localhost:8000/docs"
echo "[aurora] api log: $LOG_DIR/api.log"
echo "[aurora] ui log: $LOG_DIR/ui.log"

if [ "$FOLLOW_LOGS" -eq 0 ]; then
  echo "[aurora] startup complete"
  echo "[aurora] stop services: ./scripts/dev-down.sh"
  echo "[aurora] stream logs: ./scripts/dev-up.sh --follow-logs"
  CLEANUP_ON_EXIT=0
  exit 0
fi

echo "[aurora] following logs, press Ctrl+C to stop log streaming and local services"

follow_file "api" "$LOG_DIR/api.log"
follow_file "ui" "$LOG_DIR/ui.log"
follow_infra_logs

wait
