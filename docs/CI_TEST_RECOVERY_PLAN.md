# CI / Test Recovery Plan

## Текущие workflow
- `.github/workflows/ci.yml`: `lint-and-static`, `backend-tests`, `frontend-tests`, `smoke-compose`.

## Наблюдавшиеся неудачные задания
- `backend-tests`: падения `pytest` из-за `sqlite3.OperationalError: attempt to write a readonly database`.
- `backend-tests`: падения критических тестов по idempotency/X-Tenant из-за рассинхрона ожиданий и поведения.

## Группы неудачных заданий
- Окружение/настройка: общий SQLite-файл в `/tmp` переиспользовался между тестами.
- Импорт/путь: не обнаружено блокирующих ошибок.
- Миграции/схема: конфликт idempotency-ограничений на уровне модели и фактического контракта API.
- Unit/Integration backend: несогласованные ожидания по форме ошибок и enum/string статусам.
- Frontend/e2e: baseline оставлен в существующем контуре, критический фокус текущего этапа — backend/CI-стабильность.

## Первопричины
1. Нестабильная test DB (readonly/lock race).
2. Слишком широкий idempotency key scope (tenant+key) конфликтовал между разными endpoint.
3. Несколько тестов ожидали устаревший формат ответов (`detail.code`) и enum-представление.

## Блокирующие факторы
- Невозможность получить стабильный прогон backend-тестов.
- Непредсказуемое поведение CI из-за инфраструктурного шума.

## План восстановления (приоритет)
1. Изоляция test DB на каждый тестовый app fixture.
2. Нормализация idempotency scope до `(tenant, endpoint, key)`.
3. Актуализация тестовых ожиданий под стабильный API-контракт.
4. Стандартизация CI-джобов + артефактов отчетов.
5. Документация baseline/quarantine/gaps.
