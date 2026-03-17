#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs/dsw"
API_LOG="$LOG_DIR/api.log"
UI_BUILD_LOG="$LOG_DIR/ui-build.log"
UI_LOG="$LOG_DIR/ui.log"

mkdir -p "$LOG_DIR"

: "${NEXT_PUBLIC_API_BASE_URL:?NEXT_PUBLIC_API_BASE_URL is required}"
: "${SQLALCHEMY_DATABASE_URI:?SQLALCHEMY_DATABASE_URI is required}"
: "${REDIS_HOST:?REDIS_HOST is required}"

cd "$ROOT_DIR/api"
export PYTHONPATH="$ROOT_DIR/api"
alembic upgrade head
nohup ./run.sh >"$API_LOG" 2>&1 &

cd "$ROOT_DIR/ui"
NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" npm run build >"$UI_BUILD_LOG" 2>&1
nohup env NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL" npm run start -- --hostname 0.0.0.0 --port 3000 >"$UI_LOG" 2>&1 &

cat <<EOF
[aurora] DSW app stack started
[aurora] api log: $API_LOG
[aurora] ui build log: $UI_BUILD_LOG
[aurora] ui log: $UI_LOG
[aurora] ui port: 3000
[aurora] api port: 8000
EOF
