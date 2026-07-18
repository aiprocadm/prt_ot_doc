# Operations

## Health endpoints
- Liveness: `/healthz`
- Readiness: `/readyz`

## Backup/restore
- Используйте backup registry и restore test в ops API.
- Проверяйте историю запусков и статусы выполнения.

## Rollout / rollback
- Перед релизом: миграции, smoke, readiness.
- При rollback откатывайте миграции и выключайте новые write-paths feature flag-ами.
