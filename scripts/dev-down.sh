#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs/dev"
COMPOSE_PROJECT="aurora-local"
COMPOSE_ENV_FILE=".env.example"
COMPOSE_FILES=("$ROOT_DIR/docker-compose.yml" "$ROOT_DIR/docker-compose.dev.yml")
export AURORA_SANDBOX_IMAGE="aurora-sandbox-local"
export AURORA_REDIS_VOLUME="aurora_local_redis_data"
export AURORA_POSTGRES_VOLUME="aurora_local_postgres_data"
export AURORA_NETWORK_NAME="aurora-local-network"

run_compose() {
  local compose_args=(
    -p "$COMPOSE_PROJECT"
    --env-file "$COMPOSE_ENV_FILE"
  )
  local compose_file

  for compose_file in "${COMPOSE_FILES[@]}"; do
    compose_args+=(-f "$compose_file")
  done

  docker compose "${compose_args[@]}" "$@"
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
    kill "$pid" || true
  fi
}

stop_pid() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    kill_process_tree "$pid"
    rm -f "$pid_file"
  fi
}

stop_pid "$LOG_DIR/api.pid"
stop_pid "$LOG_DIR/ui.pid"

cd "$ROOT_DIR"
run_compose down
