#!/usr/bin/env bash
# Bootstrap the AI Running Coach for local development.
# Creates a virtualenv, installs dependencies, prepares .env and the database.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
VENV_DIR=".venv"

echo "==> Creating virtualenv in ${VENV_DIR}"
if [ ! -d "${VENV_DIR}" ]; then
  "${PYTHON}" -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "==> Upgrading pip"
pip install --quiet --upgrade pip

echo "==> Installing dependencies"
if [ "${DEV:-1}" = "1" ]; then
  pip install --quiet -r requirements-dev.txt
else
  pip install --quiet -r requirements.txt
fi

if [ ! -f ".env" ]; then
  echo "==> Creating .env from .env.example (edit it to add your credentials)"
  cp .env.example .env
fi

echo "==> Initialising the database and importing demo data"
python -m app.cli ingest

cat <<'EOF'

✅ Bootstrap complete.

Next steps:
  source .venv/bin/activate
  python -m app.cli analyze        # analyse the latest run
  python -m app.cli weekly         # weekly analysis + plan
  python -m app.cli serve          # launch the dashboard at http://127.0.0.1:8000

The app runs in DEMO mode until you add GARMIN_* and ANTHROPIC_API_KEY to .env.
EOF
