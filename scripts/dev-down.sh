#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs/dev"
COMPOSE_PROJECT="aurora-local"
COMPOSE_ENV_FILE=".env.example"
export AURORA_SANDBOX_IMAGE="aurora-sandbox-local"
export AURORA_REDIS_VOLUME="aurora_local_redis_data"
export AURORA_POSTGRES_VOLUME="aurora_local_postgres_data"
export AURORA_NETWORK_NAME="aurora-local-network"

stop_pid() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
    fi
    rm -f "$pid_file"
  fi
}

stop_pid "$LOG_DIR/api.pid"
stop_pid "$LOG_DIR/ui.pid"

cd "$ROOT_DIR"
docker compose -p "$COMPOSE_PROJECT" --env-file "$COMPOSE_ENV_FILE" down
