# KNOWN LIMITATIONS (RC)

## Backend
- `scripts/codex_audit.sh` не полностью зелёный: `tests/test_documents_status_flow.py` и `tests/test_templates_pipeline_api.py::test_tenant_listing` получают `400 TENANT_REQUIRED` без `X-Tenant`; нужен отдельный цикл выравнивания тестовых предпосылок/контракта публичных маршрутов.
- Inbound webhook paths используют fallback tenant resolution (default/test tenant) для внешних callback'ов без `X-Tenant`; это осознанная архитектурная оговорка для интеграций.

## Frontend
- Production build стабилен.
- В этом проходе не выполнялись frontend e2e/smoke через браузерный раннер.

## DevOps / Smoke
- `scripts/smoke.sh` не стартует backend автоматически; требует предварительно поднятого API на `localhost:8000`.

## Внешние интеграции
- Для полноценной проверки внешних webhook/EDO провайдеров нужны реальные внешние источники событий; локально верифицирован только внутренний ingestion-контур.
