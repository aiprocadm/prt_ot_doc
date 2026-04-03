# Риски регрессий и смягчение

| Изменение | Риск | Митигация |
|-----------|------|-----------|
| Ужесточение `APP_ENV=staging` | Staging не поднимается со старым `.env` | Обновить секреты по `CONFIGURATION_HARDENING.md`; временно использовать `development` только для локалки |
| `bootstrap()` → `SettingsError` | Редко: узкий `except` не на `RuntimeError` | `SettingsError` наследует `RuntimeError` — обратная совместимость сохранена |
| Импорт `func` в router | Поведение не меняется | Регрессионные тесты на эндпоинты usage шаблонов (добавить при появлении API-тестов) |
| Декомпозиция `tasks.py` (будущее) | Celery не находит задачи | Сохранить точки входа и имена задач; contract-тест импорта `app.tasks` |
| Рефакторинг tenant middleware | Ложные 403/400 | Матрица путей из `TenantMiddleware._public_prefixes` + интеграционные тесты |
| Изменение `_run_coroutine` / Celery sync entry | Потеря результатов, зависания, двойной event loop | Держать зелёными `tests/test_tasks_run_coroutine.py`; не вызывать coroutine из двух потоков одновременно |
| Playwright против prod preview + PWA | Белый экран или нестабильная сессия | По умолчанию smoke на Vite dev; для preview использовать `E2E_PREVIEW=1` и осознанно про SW (см. `playwright.config.ts`) |
| Ослабление `tsc` в тестах | Падение `npm run build` / ложная уверенность | Любые правки `*.test.tsx` должны проходить `tsc --noEmit` |

## Рекомендованный чеклист перед релизом

1. `pytest` (backend) + `npm run ci` (frontend).
2. `alembic heads` (уже в CI).
3. `make smoke` или docker compose smoke (уже в CI).
4. По желанию: `E2E_START_SERVER=1 npm run e2e` в `frontend/` после `npm run e2e:install`.
5. Ручная проверка: логин, смена tenant header, документы list, 401/403.
