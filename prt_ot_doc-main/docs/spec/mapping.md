# Spec ↔ Code Mapping

| Раздел спецификации | Backend модули | Frontend экраны | Тесты |
| --- | --- | --- | --- |
| Core + Modules | `backend/app/domains`, `backend/app/models` | `/admin`, `/settings` | `tests/unit`, `tests/integration` |
| Multi‑tenancy | `backend/app/middleware/tenant.py` | N/A | `tests/integration` |
| RBAC + ABAC | `backend/app/core/security.py` | `/auth`, `/users` | `tests/unit` |
| Роли/назначения | `backend/app/api/routes/admin_users.py` | `/users` | `tests/integration` |
| Документы/шаблоны | `backend/app/domains/documents`, `backend/app/services/file_storage.py` | `/templates`, `/documents` | `tests/integration` |
| Обучение | `backend/app/domains/training` | `/training` | `tests/integration` |
| Медосмотры | `backend/app/domains/medical` | `/medical` | `tests/integration` |
| Дедлайны/обязательства | `backend/app/services/obligations.py`, `backend/app/models/obligations.py` | `/tasks` | `tests/integration`, `tests/unit` |
| Департаменты/контракты/счета | `backend/app/models/finance.py` | `/finance` | `tests/integration` |
| СИЗ | `backend/app/domains/ppe` | `/ppe` | `tests/integration` |
| Инциденты | `backend/app/domains/incidents` | `/incidents` | `tests/integration` |
| Риски | `backend/app/domains/risk` | `/risks` | `tests/integration` |
| Проверки | `backend/app/domains/inspections` | `/inspections` | `tests/integration` |
| Отчёты | `backend/app/domains/reports` | `/reports` | `tests/integration` |
| Outbox/Webhooks | `backend/app/services/outbox.py` | N/A | `tests/integration` |
| WS (deferred) | `backend/app/api/routes/ws_stub.py` | N/A | `tests/integration` |
| Security | `backend/app/core/security.py` | `/auth` | `tests/unit` |
| Монетизация | `backend/app/domains/billing` | `/billing` | `tests/unit` |
