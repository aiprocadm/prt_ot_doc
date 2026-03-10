#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH=backend

run_check() {
  local title="$1"
  shift
  echo "[codex-audit] $title"
  "$@"
}

run_check "schema consistency" python scripts/verify_schema_consistency.py
run_check "tenant isolation and access guards" python -m pytest \
  tests/test_tenant_header_required.py \
  tests/test_tenant_security.py \
  tests/test_auth_tenant_header_enforcement.py \
  tests/test_middleware_tenant.py \
  tests/test_inbound_webhook_tenant_context.py \
  tests/test_next39_tenancy_enforcement.py -q
run_check "idempotency and immutable audit" python -m pytest \
  tests/test_services_idempotency_unit.py \
  tests/test_audit_log_immutability.py \
  tests/test_audit_chain_and_diff.py -q
run_check "template/document pipeline safety" python -m pytest \
  tests/test_template_delete.py \
  tests/test_documents_status_flow.py \
  tests/test_templates_pipeline_api.py -q
run_check "webhook/outbox duplicate safety" python -m pytest \
  tests/test_webhooks_dispatch.py \
  tests/test_next43_outbox_webhooks.py -q
run_check "backend module smoke checks" python -m pytest \
  backend/tests/test_tenant_core_mvp.py \
  backend/tests/test_next42_rbac_abac_audit.py \
  backend/tests/test_next39_pipeline_orchestrator.py \
  backend/tests/test_files_module_basics.py -q

echo "[codex-audit] done"
