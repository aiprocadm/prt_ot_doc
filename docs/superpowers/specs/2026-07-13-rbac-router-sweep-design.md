# RBAC router sweep — design spec

**Date:** 2026-07-13
**Branch:** `fix/rbac-router-sweep` (off `origin/main` @ 8ca7b9ef)
**Related precedent:** commit `618614d9` (RBAC guards on `/analytics` + `/exports`)

> Note: this repo is public. Lower-severity, still-open hardening items found during
> the audit (a different bug class) are **not** enumerated here; they are tracked as
> separate internal tasks. This spec documents only the fixes shipped on this branch.

## Problem

Follow-up to the 2026-07-10 spec↔code review that found `/analytics` and `/exports`
protected only by `get_session` + `get_tenant_record` (no role guard). A systematic
per-endpoint audit of every router registered in `backend/app/api/v1/route_groups.py`
(~65 router files) found the same class of gap in 12 more routers.

### How auth works here (relevant to the fix)

- Authentication *and* authorization are enforced inside the `rbac()` / `abac()`
  dependency; `get_session` / `get_tenant_record` only resolve the tenant from the
  `X-Tenant` header. Adding an `abac(...)` dependency to a route closes the gap.
- A 403 from `rbac`/`abac` surfaces as `{"code": "FORBIDDEN"}` via
  `app/api/error_handlers.py` (status→code map). This is the test contract.

## Scope (this branch)

Guard the 12 routers below. Mechanism mirrors commit `618614d9`: a module-level
`_tenant_resource_id` dependency + `abac(_tenant_resource_id, required_roles=[...],
action="...")`, applied per-endpoint (read/write split) or at router level where the
whole router shares one role set.

### Role sets

- `MGMT_READ` = `admin, owner, hr, line_manager, manager, ot_pb_lead, ot_head,
  ot_specialist, pb_engineer, accountant, auditor_ro` (mirrors `_ANALYTICS_READ_ROLES`).
- `DOC_WRITE` = `admin, owner, ot_specialist` (mirrors `_EXPORT_WRITE_ROLES` /
  report_builder `_WRITE_ROLES`).
- `ADMIN_OWNER` = `admin, owner`.
- `TENANT_ADMIN` = `admin, owner, client_admin`.
- `APPROVAL_ROLES` = `admin, employee` (mirrors `approval_orchestration` / `pep_signing`).

### Fix table

| # | Router | Endpoints | Guard |
|---|--------|-----------|-------|
| 1 | `api/routes/public_api.py` `admin_router` (`/machine-keys`) | issue/rotate/revoke/list (4) | router-level `abac(ADMIN_OWNER)` |
| 2 | `api/routes/public_api.py` `marketplace_router` (`/marketplace`) | list/publish/install (3) | router-level `abac(ADMIN_OWNER)` |
| 3 | `api/routes/approval_signing_v1.py` | whole router `/v1/*` (~30) | router-level `abac(APPROVAL_ROLES)` |
| 4 | `api/routes/client_portal.py` `internal_router` + `presets_router` | `/packages/*`, `/presets/packages/*` (7) | per-endpoint `abac` read=MGMT_READ / write=DOC_WRITE |
| 5 | `modules/replace/api.py` | whole file (11) | per-endpoint read=MGMT_READ / write=DOC_WRITE |
| 6 | `modules/packs/api.py` (`packs_v2`) | whole file (24) | per-endpoint read=MGMT_READ / write=DOC_WRITE |
| 7 | `modules/pipelines/api.py` | whole file (16) | per-endpoint read=MGMT_READ / write=DOC_WRITE |
| 8 | `modules/branding/api.py` | whole file (4) | per-endpoint read=MGMT_READ / write=DOC_WRITE |
| 9 | `api/routes/tenants.py` | `GET /tenants`, `/admin/tenants`, `/tenants/me` (3) | list→mandatory admin; `/me`→`rbac()` authn-only |
| 10 | `api/routes/ws_stub.py` | `GET /ws/v1/events` (1) | `rbac(ADMIN_OWNER)` |
| 11 | `modules/files/api.py` | `POST /{file_id}:reindex` (1) | existing module `WRITE_ACCESS_DEP` |
| 12 | `modules/search/api.py` | `POST /search/reindex[/{entity_type}]` (2) | `rbac(ADMIN_OWNER)` |

Read vs write rule: `GET` = read; `POST/PATCH/PUT/DELETE` that mutates = write;
`POST` that is pure preview/validate/compute = read.

### Deferred (documented, not fixed here)

- `documents/read.py` `POST /quality:check`, `POST /mapping:validate` — stateless
  (no tenant/DB data); accepted low risk (may be intentional pre-auth helpers).
- Additional lower-severity / different-class hardening items are tracked as separate
  internal tasks (not enumerated here — public repo).

### Follow-up — lax role granularity (resolved 2026-07-13)

These endpoints already required auth (`rbac([])`) but imposed **no role** — any
authenticated tenant user, incl. a `worker`, could perform tenant-wide config writes.
Restricted to management/specialist roles, mirroring the 618614d9 read/write sets
(`abac(_tenant_resource_id, required_roles=…)`):

| Router | Endpoint(s) | Guard |
|--------|-------------|-------|
| `notifications` | `GET /templates` / `POST /templates` | MGMT_READ / DOC_WRITE |
| `npa` | `POST /{act_id}/impact/tasks` | DOC_WRITE (reads stay authn-only) |
| `compliance` | `POST /deadlines/recompute` | ADMIN_OWNER (mirrors analytics `/recompute`) |
| `headers` | `GET /layout-presets*` / `POST·PATCH·DELETE /layout-presets*`, `POST /documents/{id}/apply-headers` | MGMT_READ / DOC_WRITE |
| `workflow` | `POST /definitions`, `/versions/{id}/publish·archive`, `POST /instances` | DOC_WRITE |

`workflow` gating is deliberately surgical: `GET /tasks` (self-scoped) and the task
actions (complete/reassign/delegate/escalate — already guarded in-service against the
task's `assignee_role_code`) stay authn-only, or a worker could not action their own
tasks. `POST /definitions/validate` is pure graph validation (no write) → authn-only.

**Self-scoped views reviewed — in-body scoping confirmed sufficient, no gating added**
(gating would break the workers they serve):
- `pwa_sync` — every write attributed to `access.user.id`, payload sanitised of
  `tenant_id`/`user_id` spoofing; `sync_status`/`resolve_conflict` gated by
  `_ensure_owner_or_admin`; `bootstrap` returns only the caller's own scoped data.
- `workspace` — `_worker_like_role` scopes worker task queries to `assignee_id ==
  user.id`; `role-summary`/`users/me/workspace` return the caller's own projection.
- `search` — query/suggest tenant-scoped via `SearchService(tenant_id=…)`;
  recent/saved scoped by `user_id`; `reindex` already gated admin/owner in the sweep.
- `tenancy` — `GET /context` returns only the caller's own tenant quota/usage; noted
  as a minor infoleak candidate (`schema_name`) but left authn-only since the frontend
  loads it globally and it is not cross-tenant.

Tests: `tests/api/test_rbac_sweep_deferred.py` (23 cases, incl. regression guards that
the un-gated self-scoped views stay open to a worker). Gates: ruff+black clean; OpenAPI
ARCH-4 unchanged (848 ops / 696 schemas).

## Test plan

Tests in `tests/api/` using the DB fixtures from `tests/conftest.py`. Contract mirrors
`tests/api/test_analytics_exports_rbac.py`:

- forbidden role (`RoleEnum.WORKER`, plus a read-only role for write endpoints) →
  `403` with `response.json()["code"] == "FORBIDDEN"`; unauthenticated → `401`.
- allowed role → `2xx`.

New test files: `tests/api/test_rbac_sweep_{docgen,portal_packages,public_api,
approval_signing_v1,misc}.py`. Two pre-existing tests that asserted the old (open)
behavior were updated to send admin auth.

## Gates

- `pytest` new + affected test files (PowerShell `.venv`, single cold-import run).
- `ruff` + `black` on changed files.
- OpenAPI ARCH-4 snapshot (`scripts/ci/check_openapi_snapshot.py`): pure security
  dependencies do not change operations/operationIds/schemas → fingerprint unchanged.

## Non-goals

- No change to the already-guarded routers.
- No refactor of the two guard vocabularies (`abac` vs `require_permission`).
