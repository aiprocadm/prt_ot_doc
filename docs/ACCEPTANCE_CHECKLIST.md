# ACCEPTANCE CHECKLIST (RC)

Статусы: ✅ выполнено · 🟡 частично · ⛔ заблокировано.

| Критерий | Статус | Подтверждение в текущем проходе | Что осталось |
|---|---|---|---|
| Повторный POST с тем же `Idempotency-Key` возвращает тот же результат | ✅ | `tests/test_idempotency.py` проходит | — |
| Любой бизнес-маршрут без `X-Tenant` -> `400` | ✅ | `tests/test_tenant_header_required.py` проходит | — |
| Выбор шаблона по `(code, version)`, конфликтное удаление -> корректная ошибка | 🟡 | `tests/test_template_delete.py` проходит | Нужен доп. прогон по версиям шаблонов и конфликтным сценариям API |
| Replace: dry-run -> apply -> rollback | 🟡 | Базовый код присутствует, но в этом проходе не закрыт end-to-end | Отдельный целевой e2e acceptance для replace |
| Статусы заданий (`queued/running/success/error/cancelled`) | 🟡 | Частично покрыто существующим набором, но не прогонялось полностью в этом цикле | Целевой прогон job-flow suite |
| Кабинет клиента: свои статусы/пакеты/файлы/история | 🟡 | Frontend build+tests стабильны | Нужен e2e с backend данными |
| Базовые dashboard/reports/export маршруты | 🟡 | Роутинг/сборка фронтенда стабильны | Нужна API+e2e в интеграционном окружении |
| CRUD потоки risk/PPE/training/incidents не ломаются | 🟡 | Нет падений фронтовых тестов по критичным страницам | Нужен backend e2e CRUD прогон |
| FE/BE контракты по ключевым разделам | 🟡 | Критичные smoke/tenant/idempotency секции согласованы | Нужен полный OpenAPI+DTO drift-pass |
| CI без критических регрессий | 🟡 | Локально зелёные: frontend lint/test/build + critical backend tests + smoke fallback gate | Полный CI run в postgres-контуре |

## Итог
RC стабилизирован по критичному минимуму, включая fallback smoke gate для dockerless среды; final sign-off требует полного CI прогона в postgres-интеграционном контуре.
