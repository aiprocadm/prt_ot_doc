# RELEASE CANDIDATE AUDIT (финальный проход)

Дата аудита: 2026-03-13.

## Что проверено
- Backend: запуск, readiness/health, ключевые tenancy/idempotency/pipeline тесты через `scripts/codex_audit.sh` и целевые pytest-сценарии.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test -- --run`, `npm run build`.
- CI/devex: локальные make-таргеты и их работоспособность без обязательной `.venv`.

## Критические проблемы, обнаруженные в ходе аудита
1. **Сбой pack-run маршрутов** (`500`) из-за импорта неверной модели PPE (`safety_core.PPEIssue` без `expires_at`) в `api/routes/packs.py`.
2. **Регрессия tenant S3 key prefix** (`tenants/...` vs ожидаемое `tenant/...`) ломала блок файловых тестов.
3. **Тестовая инфраструктура маскировала отсутствие `X-Tenant`** из-за дефолтного заголовка в `tests/conftest.py`.
4. **DX/CI проблема make lint**: при отсутствии `.venv` таргеты падали до запуска инструментов.

## Что исправлено
- Исправлен импорт в pack-run API на canonical-модель `models.PPEIssue` + `PPEIssueStatus`.
- Восстановлен префикс tenant-ключей для файлового storage (`tenant/...`) с сохранением проверки legacy/current префиксов.
- Убран дефолтный `x-tenant` из `async_client` фикстуры, чтобы тесты tenancy реально валидировали отсутствие заголовка.
- Makefile теперь корректно использует `.venv/bin/*` при наличии и fallback на системные бинарники при отсутствии `.venv`.

## Итог по стабилизации
- Стабилизированы и подтверждены важные блоки: файлы, tenancy-header проверки, pack run enqueue/idempotency, frontend build/typecheck/tests.
- Полный `pytest -q` всё ещё содержит красные блоки (ABAC/audit deny details, pack download ACL, replace dry-run endpoint, policy engine reason codes, часть graph validation).

## Остаточные риски (не скрываются)
- Неполная согласованность ABAC/error-contract между тестами и фактической схемой ошибок.
- Часть integration/API сценариев остаётся нестабильной для релиз-кандидата без дополнительного цикла исправлений.
- Линтинг backend/tests остаётся значительно красным (исторический technical debt).
