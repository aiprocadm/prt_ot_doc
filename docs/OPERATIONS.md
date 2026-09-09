# Operations

## Health endpoints
- Liveness: `/healthz`
- Readiness: `/readyz`

## Backup/restore
- **Продукт резервным копированием и восстановлением НЕ управляет** (проверено
  срезом-130: ни ручек, ни моделей, ни задач в коде нет). Прежняя строка про
  «backup registry и restore test в ops API» описывала то, чего не существует.
- Снимки базы и объектного хранилища делает окружение, в котором развёрнут
  продукт.
- Проверить, что из снимка действительно поднимается рабочая система, помогает
  учение: `python scripts/restore_drill.py --mode sqlite|postgres-minio`
  (оно же — workflow `restore-drill.yml`).
- Проверяйте историю запусков и статусы выполнения.

## Rollout / rollback
- Перед релизом: миграции, smoke, readiness.
- При rollback откатывайте миграции и выключайте новые write-paths feature flag-ами.
