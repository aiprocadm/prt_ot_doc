# Demo walkthrough 3: ЭДО + подписи + согласования

1. Создайте маршрут согласования:
   - `POST /api/v1/approvals/routes` с `code`, `name`, `rules_json.steps`.
2. Запустите согласование:
   - `POST /api/v1/approvals/requests` с `document_version_id` и `route_code`.
3. Примите решение:
   - `POST /api/v1/approvals/requests/{id}/decide` с `approve|reject|delegate`.
4. Подпишите документ (MVP):
   - `POST /api/v1/signatures` с `type=INTERNAL`.
5. Отправьте в ЭДО (mock provider):
   - `POST /api/v1/edo/send` с `provider_code=mock`.
6. Примите webhook статуса ЭДО:
   - `POST /api/v1/edo/webhooks/{provider_code}` с `event_id`, `external_id`, `status`.
7. Проверьте обновление статусов в UI:
   - `/approvals/inbox`, `/signatures`, `/edo`.
