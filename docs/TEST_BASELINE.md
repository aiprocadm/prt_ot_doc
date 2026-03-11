# Test Baseline

## must-pass (блокирующий CI)
- `lint-and-static` (scoped query guard).
- `backend-tests` (`pytest`, с JUnit-отчетом).
- `frontend-tests` (`npm run ci`).
- `smoke-compose` (`make smoke`).

## quarantine (временно неблокирующие)
- Полный e2e beyond smoke (если длительность/флак влияет на PR latency).
- Любые time-sensitive сценарии, пока не зафиксированы deterministic clock fixtures.

> Карантин применяется только по явной причине нестабильности и должен сопровождаться issue/задачей на возврат в must-pass.

## Недостаточное критическое покрытие (по ТЗ)
- Явные smoke-тесты на dry-run/apply/rollback replace в обязательном контуре.
- Дополнительные контрактные тесты signed URL/files/exports на cross-tenant leakage.
- Формализованный e2e сценарий "RBAC deny" как обязательный gate.
