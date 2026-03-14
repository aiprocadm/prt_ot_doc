# ACCEPTANCE CHECKLIST (RC)

Статусы: ✅ выполнено · 🟡 частично · ⛔ заблокировано.

| Критерий | Статус | Что подтверждено | Что осталось |
|---|---|---|---|
| Повторный POST с тем же `Idempotency-Key` возвращает тот же результат | ✅ | Покрыто `tests/test_idempotency.py` (пройдено) | — |
| Любой бизнес-маршрут без `X-Tenant` -> `400` | ✅ | Подтверждено целевыми тестами tenancy и обновленным `test_ws_stub` | Допроход полного набора всех API-маршрутов |
| Шаблон по `(code, version)`, конфликтное удаление -> корректная ошибка | 🟡 | Частично покрывается существующим набором тестов шаблонов | Нужен отдельный targeted прогон всего шаблонного контура |
| Replace: dry-run -> apply -> rollback | 🟡 | Базовые pipeline/idempotency сценарии стабильны | Полный acceptance для replace API не запускался в этом цикле |
| Статусы DocumentJob (`queued/running/success/error/cancelled`) | ✅ | Пройден `tests/integration/test_job_status_flow.py` | — |
| Кабинет клиента: свои статусы/пакеты/файлы/история | 🟡 | Базовая frontend стабильность подтверждена (lint/typecheck/tests/build) | Нужен полноценный e2e client-portal проход |
| Dashboard / reports / export маршруты работают | 🟡 | Нет падений frontend build/tests по маршрутизации | Нужен целевой API + e2e smoke экспортов/отчетов |
| Risk map / PPE / training / incidents CRUD не ломают поток | 🟡 | Unit/integration frontend тесты зеленые | Нужен backend CRUD e2e прогон по всем доменам |
| Frontend и backend не расходятся по ключевым разделам | 🟡 | Устранено одно контрактное расхождение (WS stub tenancy) | Нужен полный DTO/OpenAPI drift-pass для всех сущностей |
| CI без критических регрессий | 🟡 | Локально стабилен набор lint/typecheck/build/frontend-tests + critical backend tests | Не завершен полный `pytest -q` + полный infra smoke |

## Итог
RC стабилизирован по критическим потокам, но требует финального полного CI-прогона в целевой инфраструктуре перед release sign-off.
