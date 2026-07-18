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
| R11 | Login → tenant → список документов (+ опционально карточка) | e2e | `frontend/e2e/smoke.spec.ts`: **R11 login happy path**, **R11 documents list after login** |
| R12 | Пользователь без DOCUMENT_VIEW → страница «Доступ ограничен» | e2e | `frontend/e2e/smoke.spec.ts`: **R12 limited user denied on documents route** |
| R13 | Логин с неверным паролем → inline-ошибка у поля пароля, остаёмся на `/auth/login` | e2e | `frontend/e2e/smoke.spec.ts`: **login wrong password shows inline error** (`E2E_USER_EMAIL`) |

## Playwright: переменные окружения (R11–R13)

| Переменная | Нужна для | Примечание |
|------------|-----------|------------|
| `E2E_START_SERVER=1` | Локально / CI без внешнего URL | Поднимает Vite (`playwright.config.ts`) |
| `E2E_BASE_URL` | Альтернатива | Непустой URL; пустая строка игнорируется, см. `playwright.config.ts` |
| `E2E_PREVIEW=1` | Опционально | Сборка + preview вместо dev |
| `E2E_USER_EMAIL`, `E2E_USER_PASSWORD` | **R11** | Учётка с доступом к `/documents` |
| `E2E_USER_EMAIL` | **R13** | Только email: пароль в тесте заведомо неверный |
| `E2E_LIMITED_USER_EMAIL`, `E2E_LIMITED_USER_PASSWORD` | **R12** | Учётка без `DOCUMENT_VIEW` |
| `E2E_TENANT` | R11, R12, R13 | По умолчанию `demo` |

Команда (из корня репозитория): `E2E_START_SERVER=1 E2E_USER_EMAIL=... E2E_USER_PASSWORD=... npm --prefix frontend run e2e`.  
Для R12 добавьте `E2E_LIMITED_*`.

## GitHub Actions

Workflow [`.github/workflows/e2e-smoke.yml`](../../.github/workflows/e2e-smoke.yml): без секретов выполняются сценарии без логина (страница входа, редирект с `/documents`).  
Чтобы гонять **R11/R12** в CI, задайте в репозитории secrets: `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, `E2E_LIMITED_USER_EMAIL`, `E2E_LIMITED_USER_PASSWORD`, при необходимости `E2E_TENANT`.

## Приоритет дальнейшего E2E

1. R8 (search sidebar) — при появлении стабильных селекторов в UI.
2. Расширение R11 (wizard / генерация) — по `STABILIZATION_PLAN.md`.
