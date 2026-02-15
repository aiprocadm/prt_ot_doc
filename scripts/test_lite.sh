#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
fi

ENV_BACKUP="$(mktemp)"
cp .env "$ENV_BACKUP"
trap 'cp "$ENV_BACKUP" .env; rm -f "$ENV_BACKUP"' EXIT
cp .env.example .env

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

source .venv/bin/activate
REQ_STAMP=".venv/.requirements.stamp"
if [ ! -f "$REQ_STAMP" ] || [ requirements.txt -nt "$REQ_STAMP" ] || [ requirements-dev.txt -nt "$REQ_STAMP" ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt -r requirements-dev.txt
  touch "$REQ_STAMP"
else
  echo "Python dependencies are up to date (.venv)."
fi

# Keep test process deterministic and independent from dockerless runtime defaults.
unset APP_RUN_MODE DATABASE_URL ENABLE_METRICS
export APP_ENV=test
export REDIS_URL=memory://
export REDIS_RESULT_URL=cache+memory://
export RATE_LIMIT_STORAGE_URI=memory://

pytest

FRONTEND_STAMP="frontend/.npm-ci.stamp"
if [ ! -d "frontend/node_modules" ] || [ ! -f "$FRONTEND_STAMP" ] || [ frontend/package-lock.json -nt "$FRONTEND_STAMP" ]; then
  (cd frontend && npm ci)
  touch "$FRONTEND_STAMP"
else
  echo "Frontend dependencies are up to date (frontend/node_modules)."
fi

(cd frontend && npm run test)
