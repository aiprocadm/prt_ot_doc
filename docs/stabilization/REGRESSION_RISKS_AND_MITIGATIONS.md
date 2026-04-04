# Риски регрессий и смягчение

**Обновлено:** 2026-04-04  

| Изменение | Риск | Митигация |
|-----------|------|-----------|
| Ужесточение `APP_ENV=staging` | Staging не поднимается со старым `.env` | `CONFIGURATION_HARDENING.md`; локально допустим `development` |
| `bootstrap()` → `SettingsError` | Редко: узкий `except` не на `RuntimeError` | `SettingsError` наследует `RuntimeError` — совместимость сохранена |
| Импорт `func` в router | Поведение не меняется | Регрессионные тесты на затронутые эндпоинты |
| Декомпозиция `tasks.py` | Celery не находит задачи | Пакет `app/tasks/` + `import app.tasks`; тест `tests/test_tasks_package_import.py`; monkeypatch фона — `app.tasks._core` |
| Рефакторинг tenant middleware | Ложные 403/400 | `TenantMiddleware._public_prefixes` + интеграционные тесты |
| Изменение `_run_coroutine` / Celery sync entry | Потеря результатов, зависания, двойной event loop | Держать зелёными `tests/test_tasks_run_coroutine.py` |
| Playwright против prod preview + PWA | Нестабильная сессия / SW | `E2E_PREVIEW=1` осознанно; см. `playwright.config.ts` |
| Ослабление `tsc` в тестах | Ложная уверенность | Правки `*.test.tsx` проходят `tsc --noEmit` |
| Guard `PipelineRun` / `DocumentJob` vs session tenant | Ложный mismatch при баге гидрации сессии | Celery/async session всегда проставляет `tenant_id`; `test_tasks_pipeline_run_tenant_guard.py` |
| Новые поля в `DocumentReadinessRead` (`pipeline_stages`) | Старые клиенты игнорируют поле | Обратная совместимость: поле опционально на клиенте; сервер всегда может отдавать список |
| `enforce_row_belongs_to_tenant` на jobs/files/webhooks | 404 вместо 403 там, где раньше отличались статусы | Намеренно «не раскрывать» чужой ресурс; зафиксировать в API-тестах ожидаемый статус |
| Единый API error contract (этап 6) | Клиенты парсят старый `detail` | Версионирование ответа или поэтапная миграция + dual-read на фронте |
| Расширение mypy | Красный CI | Staged directories + `ignore_errors` overrides модульно |

## Рекомендованный чеклист перед релизом

1. `pytest` (backend) + `npm run ci` (frontend).
2. `alembic heads` (если есть в CI).
3. Docker / compose smoke при наличии в pipeline.
4. Опционально: `E2E_START_SERVER=1 npm run e2e` в `frontend/`.
5. Ручная проверка: логин, `X-Tenant`, список документов, 401/403.
