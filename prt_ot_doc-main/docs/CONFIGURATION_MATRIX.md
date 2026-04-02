# CONFIGURATION_MATRIX

Единый конфиг-слой: `backend/app/core/config.py`

Домены:
- App/API
- DB
- Redis/Celery
- Storage (local/S3)
- Webhooks
- Auth/JWT
- Billing/Quotas
- Feature toggles (demo/admin bootstrap)
- Observability/logging

Production hardening:
- запрещён `debug`;
- обязательные secrets;
- запрещён demo bootstrap без явного флага.
