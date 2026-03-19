# Release readiness

## Ready now
- Repository roots and entrypoints are explicit and documented.
- Frontend root/package manifest location is canonical and verified.
- Branding → preset → preview → apply-headers flow is implemented and regression-tested.
- Company/site inheritance and watermark reproducibility are covered by automated backend tests.
- Operator UI exists for both branding maintenance and layout preset maintenance.

## Mandatory checks before production cutover
- Run full backend test suite.
- Run frontend `typecheck`, `test`, `build`.
- Apply Alembic migrations against a production-like PostgreSQL instance.
- Validate Redis/Celery/MinIO/LibreOffice/ClamAV integrations in an integration environment.
- Execute a branded-document smoke: organization -> branch -> preset -> preview -> apply headers -> PDF.

## Recommended next wave
- Browser E2E for branded issuance.
- Richer preview/download artifacts.
- Preset import/export and revision history.
