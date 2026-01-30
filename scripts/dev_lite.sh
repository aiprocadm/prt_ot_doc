#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/configure_dockerless_env.sh .env

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt

(cd frontend && npm install)

source ./scripts/dockerless_env.sh

PYTHONPATH=backend python -m alembic -c backend/app/migrations/alembic.ini upgrade head

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

(cd frontend && npm run dev -- --host 0.0.0.0 --port 5173) &
FRONT_PID=$!

trap 'kill "$BACK_PID" "$FRONT_PID"' INT TERM
wait "$BACK_PID" "$FRONT_PID"
