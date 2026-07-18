# RESTORE_TENANT

Проверки: backup snapshot integrity, tenant isolation.
Действия: restore в staging, validation smoke, затем controlled prod restore.

Стабилизационный drill и формат evidence: `docs/stabilization/restore-drill.md`.
JSON evidence артефакты: `artifacts/restore-drill/`.
