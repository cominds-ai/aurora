#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(cd "$ROOT_DIR/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs/dsw"
RUN_DIR="$LOG_DIR/run"
API_LOG="$LOG_DIR/api.log"
UI_BUILD_LOG="$LOG_DIR/ui-build.log"
UI_LOG="$LOG_DIR/ui.log"
API_PID_FILE="$RUN_DIR/api.pid"
UI_PID_FILE="$RUN_DIR/ui.pid"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-3000}"

mkdir -p "$LOG_DIR" "$RUN_DIR"

load_env_file() {
  local file="$1"
  if [ -f "$file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$file"
    set +a
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

ensure_port_free() {
  local port="$1"
  local pids

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v ss >/dev/null 2>&1; then
    pids="$(ss -ltnp "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true)"
  else
    pids=""
  fi

  if [ -z "$pids" ]; then
    return
  fi

  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done

  sleep 1

  if command -v lsof >/dev/null 2>&1 && lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
  elif command -v ss >/dev/null 2>&1; then
    pids="$(ss -ltnp "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true)"
    if [ -n "$pids" ]; then
      for pid in $pids; do
        kill -9 "$pid" 2>/dev/null || true
      done
    fi
  fi

  sleep 1
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local retries="${3:-60}"

  for _ in $(seq 1 "$retries"); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "[aurora] $label failed to become ready: $url" >&2
  return 1
}

load_env_file "$ROOT_DIR/.env"
load_env_file "$ROOT_DIR/.aurora-secrets.env"
load_env_file "$PARENT_DIR/.aurora-secrets.env"

: "${NEXT_PUBLIC_API_BASE_URL:?NEXT_PUBLIC_API_BASE_URL is required}"
: "${SQLALCHEMY_DATABASE_URI:?SQLALCHEMY_DATABASE_URI is required}"
: "${REDIS_HOST:?REDIS_HOST is required}"

stop_pid_file "$API_PID_FILE"
stop_pid_file "$UI_PID_FILE"
ensure_port_free "$API_PORT" "api"
ensure_port_free "$UI_PORT" "ui"

cd "$ROOT_DIR/api"
export PATH="$ROOT_DIR/api/.venv/bin:$PATH"
export PYTHONPATH="$ROOT_DIR/api"
alembic upgrade head
nohup env ENV="${ENV:-production}" PYTHONPATH="$ROOT_DIR/api" SKIP_STARTUP_MIGRATIONS=1 bash ./run.sh >"$API_LOG" 2>&1 &
echo $! >"$API_PID_FILE"

if ! wait_for_http "http://127.0.0.1:${API_PORT}/api/status" "api" 60; then
  tail -n 80 "$API_LOG" || true
  exit 1
fi

cd "$ROOT_DIR/ui"
NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" npm run build >"$UI_BUILD_LOG" 2>&1
nohup env NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" npm run start -- --hostname 0.0.0.0 --port 3000 >"$UI_LOG" 2>&1 &
echo $! >"$UI_PID_FILE"

if ! wait_for_http "http://127.0.0.1:${UI_PORT}" "ui" 60; then
  tail -n 80 "$UI_BUILD_LOG" || true
  tail -n 80 "$UI_LOG" || true
  exit 1
fi

cat <<EOF
[aurora] DSW app stack started
[aurora] api log: $API_LOG
[aurora] ui build log: $UI_BUILD_LOG
[aurora] ui log: $UI_LOG
[aurora] ui port: $UI_PORT
[aurora] api port: $API_PORT
EOF
