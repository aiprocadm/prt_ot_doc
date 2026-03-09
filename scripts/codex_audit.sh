#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH=backend

echo "[codex-audit] schema consistency"
python scripts/verify_schema_consistency.py

echo "[codex-audit] critical tenancy/access tests"
python -m pytest \
  tests/test_tenant_header_required.py \
  tests/test_tenant_security.py \
  tests/test_next39_tenancy_enforcement.py -q

echo "[codex-audit] webhook critical tests"
python -m pytest tests/test_webhooks_dispatch.py -q

echo "[codex-audit] done"
