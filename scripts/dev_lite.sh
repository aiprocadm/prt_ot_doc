#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/configure_dockerless_env.sh .env

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

FRONTEND_STAMP="frontend/.npm-ci.stamp"
if [ ! -d "frontend/node_modules" ] || [ ! -f "$FRONTEND_STAMP" ] || [ frontend/package-lock.json -nt "$FRONTEND_STAMP" ]; then
  (cd frontend && npm ci)
  touch "$FRONTEND_STAMP"
else
  echo "Frontend dependencies are up to date (frontend/node_modules)."
fi

source ./scripts/dockerless_env.sh

if [[ "${DATABASE_URL}" == sqlite+aiosqlite:///./* ]]; then
  SQLITE_PATH="${DATABASE_URL#sqlite+aiosqlite:///./}"
  if [[ "${KEEP_DB:-0}" == "1" ]]; then
    echo "KEEP_DB=1 -> preserving existing sqlite database at $SQLITE_PATH"
  else
    rm -f "$SQLITE_PATH"
  fi
fi

echo ""
echo "Dockerless mode enabled"
echo "- Database: $DATABASE_URL"
echo "- Storage: $STORAGE_BACKEND ($STORAGE_ROOT)"
echo "- Celery eager: $CELERY_EAGER"
echo "- Redis: disabled"
echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""

PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACK_PID=$!

BACKEND_READY=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo "Backend ready: http://127.0.0.1:8000/health"
    BACKEND_READY=1
    break
  fi
  sleep 1
done
if [[ "$BACKEND_READY" != "1" ]]; then
  echo "Backend health check timed out (continuing; inspect backend logs)."
fi

(cd frontend && npm run dev -- --host 0.0.0.0 --port 5173) &
FRONT_PID=$!

trap 'kill "$BACK_PID" "$FRONT_PID"' INT TERM
wait "$BACK_PID" "$FRONT_PID"
