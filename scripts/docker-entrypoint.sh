#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  python -m alembic -c app/migrations/alembic.ini upgrade head
fi

exec "$@"
