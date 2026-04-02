#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  python -m alembic -c backend/app/migrations/alembic.ini upgrade heads
fi

exec "$@"
