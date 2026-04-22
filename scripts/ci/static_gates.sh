#!/usr/bin/env bash
# Узкие статические проверки: undefined names в app + поэтапный mypy для tenant-guard.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "== ruff F821 (backend/app) =="
ruff check backend/app --select F821 --no-fix

echo "== mypy staged (tenant guard + incremental API/middleware/tasks/authz-files scope, follow_imports=skip) =="
mypy --config-file pyproject.toml \
  backend/app/db/tenant_row_guard.py \
  backend/app/api/tenant_row_http.py \
  backend/app/middleware \
  backend/app/tasks \
  backend/app/celery/tasks \
  backend/app/services/tasks.py \
  backend/app/api/routes/tasks.py \
  backend/app/api/routes/files.py \
  backend/app/api/routes/admin_authz.py \
  --follow-imports=skip
