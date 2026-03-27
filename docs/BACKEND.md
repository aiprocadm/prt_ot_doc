# BACKEND

## Active runtime entrypoints
- ASGI: `backend/app/main.py`
- App factory: `backend/app/api/app.py`
- CLI: `backend/app/cli/main.py`
- Worker bootstrap: `backend/app/worker.py`
- Alembic: `backend/app/migrations/alembic.ini`
- Repo-root compatibility package: `app/__init__.py`

## Canonical backend layering
- `backend/app/api/` — HTTP entrypoints, dependency wiring, request/response schemas, router composition.
- `backend/app/modules/` — application services and module-local orchestration for active product domains.
- `backend/app/domains/` — lower-level domain logic and reusable bounded-context helpers.
- `backend/app/services/` and `backend/app/core/` — infrastructure adapters, tenancy/security support, and cross-cutting services.
- `backend/app/migrations/` — Alembic configuration and migration history.

## Document-core related modules
- `app.modules.branding` — resolves tenant/company/site inheritance into a normalized branding profile.
- `app.modules.headers` — stores layout presets and applies headers/footers to DOCX.
- `app.api.routes.documents` — legacy and orchestrated document generation routes.
- `app.tasks.apply_headers_job` — async header application job.

## Production-minded guarantees in scope
- tenant-aware queries for company/site/preset resolution;
- idempotent header application endpoint;
- reproducibility metadata returned by branding preview;
- stable branding payload hash embedded into preview reproducibility metadata;
- explicit `header_details` / `footer_details` fields in the branding profile for firm-letterhead requisites;
- site branding can override the display branch name used by rendered headers via `branch_label`;
- merge-safe branding profile updates so partial edits do not erase existing requisites/assets;
- additive API evolution: preview now returns `apply_headers_payload` and `wizard_defaults` without breaking existing clients.

## Stabilization invariants
- For FK-backed tenant-scoped models derived from `TenantBaseModel`, `tenant_id` stores `tenant.id` only. `tenant.slug` remains a routing/header identifier and must not be written into FK-backed `tenant_id` columns.
- Session tenancy context is now split into `tenant_id`, `tenant_slug`, and `tenant_schema`. Legacy `session.info["tenant"]` is preserved only as a compatibility alias for slug-oriented flows.
- Runtime schema bootstrap now respects recorded `tenant.schema_name` when a tenant uses an explicit schema override; dev bootstrap, demo bootstrap, dependency resolution, and tenant bootstrap service no longer fall back to `tenant_<slug>` when a different schema name is already configured.
- Implicit runtime schema creation through `AsyncSessionLocal(...)` is now disabled by default and guarded by `RUNTIME_SCHEMA_BOOTSTRAP=false`. Ordinary runtime paths no longer auto-create shared or tenant schemas unless this is explicitly enabled; explicit bootstrap flows still call schema creation directly.
- Demo bootstrap now seeds FK-backed entities with the resolved tenant UUID instead of the tenant slug.
- Canonical auth session contract remains `TokenPair` for `/auth/login` and `/auth/refresh`; profile hydration is handled via `/auth/me` and `/auth/me/permissions`.
- Static OpenAPI in `docs/openapi.yaml` is aligned with the runtime auth contract for `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, and `/auth/me/permissions`; drift on these endpoints is guarded by contract tests.
- `POST /auth/logout` is a documented stateless endpoint: the backend acknowledges logout with `204 No Content`, while clients clear local tokens. Refresh-token revocation storage is not implemented in the current runtime.
- Credentialed CORS may not use wildcard origins. `APP_CORS_ORIGINS="*"` is rejected when `APP_CORS_ALLOW_CREDENTIALS=true`.
- Canonical frontend-facing paths are now protected from overlapping legacy aliases on the most critical route collisions. Legacy compatibility handlers were moved to explicit namespaced or versioned paths instead of shadowing active URLs.

## Known remaining gap after wave 1
- Several legacy template/pack/pipeline domains still use slug-scoped `tenant_id` semantics in their own tables and services. They were not mass-refactored in this patch because that requires a bounded migration plan and compatibility review across models, repositories, and workers.
