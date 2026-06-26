#!/usr/bin/env sh
# Production entrypoint:
#   1. (optional) restore the SQLite DB from a Litestream replica on cold start
#   2. apply database migrations
#   3. (optional) run the server under Litestream continuous replication
#   4. otherwise run the server directly
#
# Honours $PORT (set by Render/Railway/Fly) and falls back to 8000.
set -eu

PORT="${PORT:-8000}"
DB_PATH="${DB_PATH:-/app/data/running_coach.db}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"
APP_USER="${APP_USER:-appuser}"

# Persistent volumes (e.g. Fly.io) are mounted root-owned. When we start as
# root, make the data dir writable by the unprivileged user and re-exec as them
# via gosu so the actual server never runs as root. The id check prevents an
# infinite loop after privileges are dropped.
DATA_DIR="$(dirname "$DB_PATH")"
mkdir -p "$DATA_DIR"
if [ "$(id -u)" = "0" ]; then
  chown -R "$APP_USER":"$APP_USER" "$DATA_DIR" 2>/dev/null || true
  exec gosu "$APP_USER" "$0" "$@"
fi

LITESTREAM_CONFIG="${LITESTREAM_CONFIG:-/etc/litestream.yml}"

have_litestream() {
  command -v litestream >/dev/null 2>&1 \
    && { [ -f "$LITESTREAM_CONFIG" ] || [ -n "${LITESTREAM_REPLICA_URL:-}" ]; }
}

if have_litestream && [ ! -f "$DB_PATH" ]; then
  echo "==> Restoring database from Litestream replica"
  if [ -f "$LITESTREAM_CONFIG" ]; then
    litestream restore -if-replica-exists "$DB_PATH" || true
  else
    litestream restore -if-replica-exists -o "$DB_PATH" "$LITESTREAM_REPLICA_URL" || true
  fi
fi

echo "==> Applying database migrations"
python -m app.cli migrate

SERVER="uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --forwarded-allow-ips=${FORWARDED_ALLOW_IPS}"

if have_litestream; then
  echo "==> Starting server under Litestream replication"
  exec litestream replicate -exec "${SERVER}"
else
  echo "==> Starting server"
  exec ${SERVER}
fi
