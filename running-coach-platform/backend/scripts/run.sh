#!/usr/bin/env bash
# Convenience launcher: starts the web dashboard (creating the venv if needed).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "==> No virtualenv found, running bootstrap first"
  ./scripts/bootstrap.sh
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "==> Starting AI Running Coach on http://${HOST}:${PORT}"
exec python -m app.cli serve --host "${HOST}" --port "${PORT}"
