# CI STABILIZATION REPORT (RC)

## Что ломалось
- `make lint` падал до запуска проверок при отсутствии `.venv` (жёсткая привязка к `.venv/bin/*`).
- Полный `pytest -q` показывал каскадные падения:
  - файлы (tenant key prefix mismatch),
  - pack run (500 из-за неправильной модели PPE в инвариантах),
  - tenancy enforcement тесты маскировались дефолтным заголовком в test client.
  - webhook tenant-context тесты падали после удаления дефолтного tenant header (ожидали неявный tenant).

## Что исправлено
1. **Makefile fallback** на системные `python/pytest/ruff/black/uvicorn/alembic` если `.venv` отсутствует.
2. **Files storage prefix** восстановлен на `tenant/...` для совместимости контрактов и тестов.
3. **Pack run API** исправлен импорт PPE-модели/enum, убран 500 в ключевых сценариях enqueue/idempotency.
4. **Тестовый клиент** больше не подставляет дефолтный `x-tenant`, tenancy проверки валидны.
5. **Webhook tenant-context tests** обновлены под текущий security-контракт с обязательным `X-Tenant`.

## Стабильные этапы после правок
- `scripts/codex_audit.sh` — проходит.
- Frontend: `lint`, `typecheck`, `test`, `build` — проходят.
- Целевые backend regression блоки (files/tenancy/pack-idempotency) — проходят.

## Что остаётся нестабильным
- Полный `pytest -q` всё ещё красный (ABAC/audit deny, pack download ACL, replace API, policy-engine reason semantics, отдельные graph/profile кейсы).
- `make lint` теперь запускается, но backend/tests содержат большое историческое число ruff-нарушений (не регрессия текущего прохода, а накопленный долг).
