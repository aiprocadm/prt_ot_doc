# CI STABILIZATION REPORT (RC)

## Что ломалось
- Падали тесты `tests/test_inbound_webhook_tenant_context.py` (оба кейса) с `400` вместо ожидаемого `202/200`.
- Корневая причина: webhook callback-маршруты требовали tenant context, но не имели корректного fallback tenant resolution в ingress-пути без `X-Tenant`.

## Что исправлено
1. В `backend/app/api/dependencies.py` расширены fallback-маршруты tenant lookup для:
   - `/api/v1/webhooks/inbound/*`
   - `/api/v1/edo/webhooks/*`
   - `/api/v1/edo/webhook/status`
2. В `backend/app/middleware/tenant.py`:
   - webhook ingress добавлен в public prefixes;
   - реализована предзагрузка tenant context (`_preload_webhook_tenant`) для inbound webhook.

## Стабильные этапы после правок
- `pytest -q tests/test_inbound_webhook_tenant_context.py` — зелёный.
- `pytest -q tests/test_tenant_header_required.py tests/test_idempotency.py tests/integration/test_job_status_flow.py` — зелёный.
- `npm --prefix frontend run build` — зелёный.

## Что остаётся нестабильным / ограниченным
- `scripts/smoke.sh` падает без запущенного backend процесса (операционное ограничение запуска).
- `scripts/codex_audit.sh` остаётся частично красным: падают `tests/test_documents_status_flow.py` и `tests/test_templates_pipeline_api.py::test_tenant_listing` из-за строгого требования `X-Tenant` в запросах без tenant header.
