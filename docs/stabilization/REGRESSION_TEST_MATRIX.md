# Матрица регрессионных сценариев

Использование: перед релизом и после крупных PR в tenant/auth/documents.

| ID | Сценарий | Тип теста | Статус |
|----|----------|-----------|--------|
| R1 | Health `/health`, `/ready` | smoke / manual | CI smoke-compose |
| R2 | API без `X-Tenant` на `/api/v1/*` → 400 TENANT_REQUIRED | automated | `test_middleware_tenant` |
| R3 | JWT невалиден → структурированная ошибка | automated | middleware / auth tests |
| R4 | OpenAPI статический = runtime schema (auth paths) | automated | `test_auth_openapi_runtime_contract` |
| R5 | Staging env без dev-default секретов | automated | `test_settings_staging_hardening` |
| R6 | S3 object key включает tenant slug | automated | `integration/test_tenant_isolation` |
| R7 | Frontend 401 → redirect helper (не hard reload) | automated | `errorHandlingAuthRedirect.test.ts` |
| R8 | Search: после успешного поиска обновляется sidebar recent | manual / e2e | Проверить в UI |
| R9 | Document wizard: шаги без 500 | manual | |
| R10 | Webhook inbound с неверной подписью → отказ | automated | при наличии тестов |
| R11 | Login → tenant bootstrap → documents list | e2e | **TODO Playwright** |
| R12 | Пользователь без DOCUMENT_VIEW → нет маршрута/403 | e2e | **TODO** |

## Приоритет внедрения E2E

1. R11 (сквозной happy path).
2. R12 (permissions).
3. R8 (search sidebar).
