# Стабилизация платформы — технический аудит

Дата: 2026-04-03. Источник: обзор кода `backend/app`, `frontend/src`, `tests/`, CI, конфигурации.

## Краткое резюме

- **Критично исправлено в рамках спринта:** отсутствие импорта `sqlalchemy.func` в `backend/app/api/v1/router.py` (потенциальный `NameError` на путях подсчёта usage шаблонов).
- **Усилено:** `APP_ENV=staging` теперь проходит те же проверки «не дефолтных» секретов, что и production (кроме явных JWT-ключей — для staging допускается dev-пара с предупреждением, как и для development).
- **Документировано:** план этапов, пробелы тестов, риски регрессий, runbook, конфигурация.
- **Намеренно не сделано за один проход:** полный ruff-порог на весь `backend/app` (накопленный технический долг ~40+ замечаний), расширение mypy за пределы `services`/`schemas`, полный Playwright E2E в CI — см. `STABILIZATION_PLAN.md` и `TEST_COVERAGE_GAPS.md`.

## Таблица находок

| ID | Серьёзность | Влияние | Модуль / файлы | Риск | Статус |
|----|-------------|---------|----------------|------|--------|
| A1 | **Critical** | runtime | `api/v1/router.py` | Использование `func.count` / `func.max` без импорта `func` — падение API при вызове затронутых эндпоинтов | **Исправлено** (`from sqlalchemy import func, select`) |
| A2 | **High** | maintainability, runtime | `app/core/runtime_bootstrap.py` (`_run_coro_sync`) | Мост sync/async через отдельный поток и `asyncio.run` при уже запущенном loop — хрупко для вложенных контекстов | Зафиксировано; поэтапная замена на явный async startup |
| A3 | **High** | maintainability | `backend/app/tasks.py` (~1.5k+ строк), `models/models.py` (~2.2k+ строк) | God-объекты, сложность ревью и регрессий | План декомпозиции по доменам без смены контрактов |
| A4 | **High** | tenancy, security | Публичные префиксы в `middleware/tenant.py` | Широкие исключения для webhooks/portal/auth — необходимы периодические ревью на «обход» tenant header | Мониторинг + тесты на каждый новый публичный префикс |
| A5 | **Medium** | security, configuration | `core/config.py`, `bootstrap()` | Переменные окружения могли переопределять явные kwargs в тестах/утилитах; staging ранее не требовал смены dev-default секретов | **Частично:** staging ≈ production для SECRET/DB/S3; тесты с изоляцией env |
| A6 | **Medium** | testability | CI `lint-and-static` | Нет ruff/black/mypy gate на весь пакет — опасные ошибки (F821) проходили до runtime | Ruff в CI отложен из‑за бэклога; критичный F821 устранён точечно |
| A7 | **Medium** | observability | Metrics `/metrics` за флагом, логирование | Не везде гарантированы `tenant_id` / `user_id` в структурированных логах воркеров | Унификация контекста в `ObservabilityMiddleware` + задачи Celery |
| A8 | **Medium** | reliability | outbox, webhooks, idempotency | Требуется перекрёстная проверка terminal state retries и DLQ | См. `STABILIZATION_PLAN` фаза 3 |
| A9 | **Low** | UX, frontend | Крупные страницы, Zustand без единого data layer | Рассинхрон прав и UI при ошибках загрузки профиля | Частично снято рефакторингом Search/роутинга; TanStack Query — поэтапно |

## Сильные стороны (уже в коде)

- Middleware tenant: обязательный `X-Tenant` для `/api/v1/*`, структурированные ошибки с `correlation_id`.
- Набор тестов: `test_middleware_tenant.py`, `test_tenant_header_required.py`, `integration/test_tenant_isolation.py` (S3 keys), contract/OpenAPI тесты.
- CI: pytest, frontend `ci` script, alembic heads, docker smoke, scoped query guard, artifact guard.

## План устранения (этапы)

См. `STABILIZATION_PLAN.md`.
