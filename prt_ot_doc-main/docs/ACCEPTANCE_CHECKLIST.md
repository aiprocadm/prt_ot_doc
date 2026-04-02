# ACCEPTANCE CHECKLIST (RC)

Статусы: ✅ выполнено · 🟡 частично выполнено · ⛔ заблокировано.

| Критерий ТЗ | Статус | Что подтверждено | Что осталось |
|---|---|---|---|
| 1) Повторный POST с тем же Idempotency-Key возвращает тот же результат | ✅ | В `final_acceptance` проходит критический backend-набор, включающий `tests/test_idempotency.py`. | Дополнительно зафиксировать в GitHub CI артефактах. |
| 2) Любой бизнес-маршрут без X-Tenant -> 400 | ✅ | В `codex_audit` проходит блок tenant isolation и access guards. | Поддерживать регрессионный набор в обязательном CI-gate. |
| 3) Выбор шаблона строго по (код, версия), конфликтное удаление -> корректная ошибка | ✅ | В `final_acceptance` проходит `tests/test_template_delete.py`; в `codex_audit` проходит template/document pipeline safety. | Расширить e2e-покрытие для UI-сценария удаления. |
| 4) Replace: dry-run -> apply -> rollback | 🟡 | В этом проходе нет отдельного таргетного e2e dry-run/apply/rollback отчета. | Добавить выделенный smoke/e2e маршрут в CI. |
| 5) Задания: queued/running/success/error/cancelled корректны | 🟡 | В `codex_audit` подтвержден pipeline safety и document status flow. | Дофиксировать единый сценарий со всеми terminal states в одном smoke-тесте. |
| 6) Кабинет клиента видит свои статусы/пакеты/файлы/историю | 🟡 | В `codex_audit` проходит backend module smoke для portal-related модулей. | Нужен полноценный browser e2e на UI клиентского кабинета. |
| 7) Дашборд/отчеты/экспорт работают хотя бы базово | ✅ | `final_acceptance` проходит e2e final regression subset + sample render/pdf/export flow + frontend checks. | Расширить нефункциональные проверки производительности. |
| 8) Риски / СИЗ / обучение / инциденты / проверки не ломают базовые CRUD-потоки | 🟡 | В `codex_audit` проходит backend module smoke, включая соответствующие домены. | Добавить явный агрегированный CRUD-smoke по доменам в release pipeline. |
| 9) FE/BE контракты не расходятся по ключевым разделам | ✅ | `final_acceptance` подтверждает openapi drift check (`tests/contract/test_openapi_contract.py` + `scripts/contract/validate.py`), frontend test-gate и production build проходят. | Поддерживать snapshot-контроль контрактов как required check. |
| 10) CI не страдает от критических регрессий | 🟡 | Критические acceptance/check сценарии зеленые. | Полный `make ci-local` красный из-за исторического lint-долга; требуется отдельная стабилизация lint-stage. |
