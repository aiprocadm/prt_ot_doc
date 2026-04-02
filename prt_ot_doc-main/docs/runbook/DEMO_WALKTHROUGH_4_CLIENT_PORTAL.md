# DEMO WALKTHROUGH 4 — Client Portal (MVP)

1. Создайте пресет пакета через `POST /api/v1/presets/packages` или выполните `python scripts/seed_package_presets.py`.
2. Запустите пакет через `POST /api/v1/packages/runs` с `preset_code`.
3. Сгенерируйте ссылку для клиента: `POST /api/v1/packages/runs/{id}/portal-link`.
4. Откройте `/portal?token=...` и загрузите статус по `GET /api/v1/portal/packages`.
5. В карточке пакета откройте детали (`GET /api/v1/portal/packages/{id}`), файлы (`GET /api/v1/portal/packages/{id}/files`) и создайте тикет (`POST /api/v1/portal/packages/{id}/tickets`).

Ограничения MVP:
- доступ по портальному токену ограничен scope (`package_run_ids` + флаги `download/upload/tickets`);
- токен хранится в БД только как hash;
- срок действия токена и revoke проверяются на каждом запросе.
