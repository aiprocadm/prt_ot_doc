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

ensure_port_free() {
  local port="$1"
  local label="$2"
  local pid=""

  if command -v lsof >/dev/null 2>&1; then
    pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  fi

  if [[ -n "$pid" ]]; then
    echo "$label port $port is already in use by PID $pid. Stop the existing process and rerun ./scripts/dev_lite.sh."
    exit 1
  fi
}

ensure_port_free 8000 "Backend"
ensure_port_free 5173 "Frontend"

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

python ./scripts/run_backend_lite.py &
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
