# ACCEPTANCE CHECKLIST (RC)

Статусы: ✅ выполнено · 🟡 частично · ⛔ заблокировано.

| Критерий | Статус | Подтверждение в текущем проходе | Что осталось |
|---|---|---|---|
| Повторный POST с тем же `Idempotency-Key` возвращает тот же результат | ✅ | `tests/test_idempotency.py` green | — |
| Любой бизнес-маршрут без `X-Tenant` -> `400` | ✅ | `tests/test_tenancy_enforcement.py` green | — |
| Выбор шаблона по `(code, version)`, конфликтное удаление -> корректная ошибка | 🟡 | Базовые шаблонные тесты в проекте есть, но в этом цикле не прогонялись полным набором | Нужен targeted прогон полного template/version suite |
| Replace: dry-run -> apply -> rollback | 🟡 | Компоненты и API-маршруты присутствуют | Нужен e2e acceptance прогон replace-chain |
| Статусы заданий (`queued/running/success/error/cancelled`) | 🟡 | `tests/test_jobs_api.py` + `tests/integration/test_pipeline_idempotency.py` проходят | Нужен полный статусный e2e с cancel/error ветками |
| Кабинет клиента: свои статусы/пакеты/файлы/история | 🟡 | FE тесты/сборка стабильны | Нужен интеграционный прогон на наполненных данных |
| Dashboard/reports/export маршруты на базовом уровне работают | 🟡 | FE роутинг/рендер покрыт тестами, build проходит | Нужна backend+frontend связка на реальном стенде |
| CRUD потоки risk/PPE/training/incidents не ломаются | 🟡 | Регрессий в текущем smoke+frontend test-проходе не выявлено | Нужен расширенный API CRUD regression suite |
| FE/BE контракты по ключевым разделам | 🟡 | Устранено критическое расхождение по tenant file key (`tenants/...`) | Нужен полный DTO/OpenAPI drift pass |
| CI без критических регрессий | ✅ | Backend critical + FE lint/typecheck/test/build + smoke gate green | Закрыть оставшиеся предупреждения и провести полный CI на Postgres |

## Итог
RC доведен до стабильного критического минимума, включая устранение контракта tenancy storage-key и подтверждение базовых CI ворот. Для финального release sign-off остаются интеграционные e2e-проверки в полном стенде.
