#!/usr/bin/env bash
# Узкие статические проверки: undefined names в app + поэтапный mypy для tenant-guard.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "== ruff F821 (backend/app) =="
ruff check backend/app --select F821 --no-fix

echo "== mypy staged (tenant_row_guard + tenant_row_http, follow_imports=skip) =="
mypy --config-file pyproject.toml \
  backend/app/db/tenant_row_guard.py \
  backend/app/api/tenant_row_http.py \
  --follow-imports=skip
