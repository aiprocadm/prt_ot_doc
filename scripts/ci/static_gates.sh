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
echo "== mypy staged (wave 1: API + middleware + task paths + file/authz-sensitive modules, follow_imports=skip) =="
mypy --config-file pyproject.toml \
  backend/app/db/tenant_row_guard.py \
  backend/app/api/tenant_row_http.py \
  backend/app/api/routes/files.py \
  backend/app/middleware/tenant.py \
  backend/app/middleware/billing_guard.py \
  backend/app/middleware/global_error_handler.py \
  backend/app/middleware/observability.py \
  backend/app/tasks/__init__.py \
  backend/app/tasks/_core.py \
  backend/app/tasks_replace.py \
  backend/app/celery/tasks/document_jobs_required.py \
  backend/app/celery/tasks/job_steps.py \
  backend/app/modules/files/service.py \
  backend/app/modules/rbac_abac/query_filters.py \
  --follow-imports=skip
