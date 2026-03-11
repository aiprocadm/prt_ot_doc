# Test Baseline

## must-pass (блокирующий CI)
- `python scripts/ci/check_scoped_queries.py`
- `pytest --junitxml=artifacts/backend-junit.xml`
- `npm --prefix frontend run ci`
- `make smoke` (в CI только после `docker compose up -d --build`)

## quarantine (временный неблокирующий)
- Полный расширенный e2e beyond smoke (оставлен вне блокировки до стабилизации стенда).
- Frontend-тесты с шумными предупреждениями `act(...)` не исключены, но вынесены как технический долг (не блокируют, так как тесты зелёные).

## Критический контур, покрытый/проверенный на этом этапе
- Idempotency (повтор ключа / конфликт hash) в pipeline flow.
- Обязательность tenant context через API-заголовки.
- Header pipeline: watermark + PAGE/NUMPAGES.
- Подключение и базовая валидация PDF-конвертации endpoint (требование `Idempotency-Key`).

## Недостаточное критическое покрытие (следующий этап)
- Расширенный smoke e2e на client-portal data isolation и RBAC deny.
- Полный dry-run/apply/rollback replace как обязательная блокирующая проверка.
- Webhook dedup/consistency сценарии в обязательном smoke-наборе.
