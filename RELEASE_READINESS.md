# Release readiness

## Ready
- Backend and frontend roots are explicit and documented.
- Branded document foundation exists end-to-end: profile -> preset -> preview -> header/footer application.
- Migration included for branding persistence.
- Regression tests cover branding API and header engine.

## Before production cutover
- Run full backend and frontend CI suites.
- Apply Alembic migrations on a production-like PostgreSQL instance.
- Validate LibreOffice/PDF conversion, MinIO/S3 and Celery in integration environment.
- Add browser-level e2e for `/documents/branding` + wizard flow.
