# KNOWN_LIMITATIONS

- **Updated on (UTC):** 2026-05-21
- **Owner:** Product Engineering + Platform
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- **Canonical TZ:** `docs/spec/TZ_FULL_UNIFIED.md` (раздел A — MVP, B — vNext)

## Release-critical limitations subset

| Criterion ID | Limitation tied to release readiness | Unified status | Evidence |
|---|---|---|---|
| RC-011 | Notifications escalation/provider orchestration is not feature-complete | `missing` | Tests: `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py`; workflow: `.github/workflows/ci.yml`; tracker: `GAP_REPORT.md` |
| RC-007 | Replace dry-run/reporting path is incomplete end-to-end | `done` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md` (tests: `test_replace_api.py`, `test_replace_engine_advanced.py`); workflow: `.github/workflows/ci.yml` (`backend-tests`, `openapi-contract`); closed 2026-04-30 per `RELEASE_BLOCKERS_STATUS.md`. |
| RC-008 | PDF conversion acceptance reliability not fully closed | `done` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md` (tests: `test_documents_generate.py`, `test_pdf_idempotency.py`, `test_services_pdf_unit.py`); workflow: `.github/workflows/ci.yml` (`backend-tests`); closed 2026-04-30 per `RELEASE_BLOCKERS_STATUS.md`. |
| RC-009 | Approval/sign/archive handoff acceptance is incomplete | `done` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md` (tests in `test_approval_*.py`, `test_next57_approval_*.py`); workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; closed 2026-04-30 per `RELEASE_BLOCKERS_STATUS.md`. |

## Non-blocking limitations

Other limitations may remain `partial` without blocking release if they are not mapped in the release-blocker checklist.
See canonical mapping in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.

## Cross-links

- Release verdict: `RELEASE_READINESS.md`
- Acceptance map: `ACCEPTANCE_TEST_MATRIX.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization tracker: `docs/stabilization/PLAN.md`

## Document chain limitations (updated 2026-04-30)
- End-to-end chain state model is unified (`generated → headers_applied → pdf_ready → handoff_ready`), but legacy single-run flow still performs headers/pdf as logical orchestration milestones without a dedicated persisted artifact per milestone.
- Quick-generate timeline currently visualizes orchestration states from task metadata only; historical runs created before 2026-04-22 may not include complete timeline arrays.

## ORM↔Postgres enum-label parity — pre-existing UPPER rows need backfill (added 2026-06-02, iter-49)

52 native-enum ORM columns now bind the member `.value` (lowercase / CamelCase) via the `native_enum` helper (`backend/app/models/base.py`) / `values_callable`, matching their `pg_enum` labels; migration `20260602_iter49_enum_label_parity` adds the few genuinely-missing labels (`documentstatus`, `notificationchannel`, `notificationtype`, `roleenum`) and merges the 8 divergent heads. This is the next masked layer after the iter-38 `server_default` fix: `alembic upgrade heads` was already green, but ORM **writes** to these columns failed on Postgres (`InvalidTextRepresentationError`) because `Enum(X)` without `values_callable` binds the member NAME (UPPER) while the pg type holds lowercase/CamelCase `.value` labels. **Fresh Postgres is now fully correct** (guarded by `backend/tests/test_orm_enum_pg_label_parity.py` — live-PG subset + write guards — and `backend/tests/test_orm_enum_values_callable_parity.py` — fast no-PG pin of the 52).

- **Caveat (data migration, out of scope):** any database written *before* iter-49 may hold UPPER member-NAME strings in these columns (notably `user.role`, `user_role.role`, `document.status`). Those rows need a one-time backfill (`UPDATE … SET col = lower(col)` / explicit value mapping) to remain queryable by the ORM after the switch. The pre-release `cabinet` DB is intentionally untouched; perform the backfill before promoting any pre-iter-49 database.
- **Adjacent drift surfaced while building the live-PG write smoke (separate from enum parity) — RESOLVED 2026-06-25:** a live-PG re-audit corrected the earlier claim. Only `tenant.code` и `tenant.schema_name` реально NOT NULL на PG (миграция `20250601_tenant_quotas_and_counters` `batch.alter_column`), а `tenant.s3_prefix` остаётся **nullable** (миграция `20260221_next11` добавляет колонку nullable и не делает `alter_column` к NOT NULL — прежняя формулировка «s3_prefix NOT NULL» была неверна). Fix: ORM `Tenant.code`/`schema_name` переведены в `nullable=False` с контекстным default из `slug` (продакшен-конвенция `code=slug`, `schema_name=tenant_<slug>`); `s3_prefix` оставлен `nullable=True` (дрейфа нет).
- **Mapper-registry `Inspection` ambiguity — FIXED 2026-06-03 (`fix/orm-enum-pg-label-parity`):** `configure_mappers()` (and therefore the first ORM insert in a fresh session) raised `InvalidRequestError: Multiple classes found for path "Inspection"`, which also silently aborted the `after_configured` event in `app/db/session.py` before `register_cross_base_fk_resolution` ran (disabling bare-name cross-base FK resolution). Fixed by qualifying the ambiguous string-keyed relationship targets (`Inspection`, `CorrectiveAction`) to fully module-qualified paths and renaming a colliding `Site.inspections` backref to `regulatory_inspections`; guarded by `backend/tests/test_orm_mapper_configuration.py`. **Still latent (re-audited 2026-06-25):** 4 mapped class names are duplicated across modules — `Inspection`, `CorrectiveAction`, `IncidentPerson`, `PlanTask` (distinct tables, intentional). `PPEIssue`/`PPENorm` больше НЕ дублируются (family-B удалён, PR #647). Ни на одно из 4 имён нет bare string-keyed `relationship("X")` (только forward-ref аннотации, которые резолвятся в globals модуля), поэтому `configure_mappers()` зелёный; первый же bare-ref сломает его снова. Набор запинен в `backend/tests/test_orm_mapper_configuration.py::test_duplicate_mapped_class_names_match_known_set`.

## CI stabilization limitations (added 2026-05-21, post-billing-restore)

GitHub Actions billing was restored on 2026-05-21 after a ~9-week block (from 2026-03-21). Eight iterations of fixes (PRs #549–#555) closed most of the surfaced rot but **three `main` CI jobs remain red** after the iter-8 merge:

- **`alembic-postgres-upgrade`** — `DuplicateObjectError: type "<enum_name>" already exists` on Postgres upgrade. Root cause: SQLAlchemy `sa.Enum(...)` emits an extra `CREATE TYPE` after an earlier explicit `postgresql.ENUM(...).create(checkfirst=True)`. PR #555 fixed 7 migrations using `postgresql.ENUM(..., create_type=False)`; additional migrations with the same pattern are suspected (iter-9 candidate). Until this is green, **no release-blocker workflow re-validation can succeed** because backend boot fails.
  - **UPDATE 2026-06-01 (RESOLVED on local PG16 — branch `fix/iter38-enum-server-default-case`, commit `54cae5c`):** Reproduced canonically on a fresh Postgres 16 and fixed. The old `DuplicateObjectError` was already gone (`8d2c1a6c5e24` uses `create_type=False`). A fresh `alembic upgrade heads` had **never** run green (suite is SQLite-only, hiding PG enum semantics; CI off since 2026-05-28), exposing **5 stacked PG-only bugs**, each masked by the prior under env.py's single outer transaction: (1) iter38 enum `server_default` UPPER-name vs lowercase-value → `InvalidTextRepresentationError`; (2) `ALTER TYPE ADD VALUE` used as a default in the same tx → `UnsafeNewEnumValueUsageError`, fixed via env.py `AUTOCOMMIT` + `transaction_per_migration=True`; (3) iter47 `file_kind` type-ordering; (4) iter43 `incidentstatus` default-cast (`DROP/ALTER/SET DEFAULT`); (5) iter42 `incidenttype`/`incidentstage` ordering. Now `upgrade heads` exits 0 (106 migrations) on fresh PG16, guarded by `backend/tests/test_alembic_postgres_upgrade.py` (first PG-executing test). ⚠️ env.py change alters upgrade atomicity (per-migration commit, not one global tx) — review before merge; downgrade not PG-tested. Canonical Py3.12.12 confirmation pending CI re-enable (W0).
  - **UPDATE 2026-06-02 (env.py review done; downgrade tested; 🔴 next layer found):** env.py atomicity reviewed — **acceptable for merge** (per-*statement* autocommit proven; no migration relies on global rollback; all 7 `ADD VALUE` are `IF NOT EXISTS`). iter43 `downgrade()` fixed (mirror of the upgrade default-dance). 🔴 **New PG-write limitation discovered:** 49/81 ORM native-enum columns lack `values_callable`, so SQLAlchemy persists UPPER member **names** while the pg_enum types hold lowercase **value** labels → `InvalidTextRepresentationError` on insert (ground-truth verified). Migrations apply and the app boots, but **inserts/updates of ~49 enum columns fail on Postgres** — invisible on SQLite (enum→VARCHAR). Tracked as a dedicated follow-up plan (fix = add `values_callable`; messy enums `roleenum`/`notifications.type`/`document.status` need per-case alignment). **"Canonical PG green" for migrations ≠ app works on PG until this closes.** See `RELEASE_BLOCKERS_STATUS.md` 2026-06-02 update + `AI_IMPLEMENTATION_REPORT.md` top handoff.
- **`perf-smoke`** — fails for the same reason transitively (smoke boot requires migrations to apply).
- **`container-image-scan`** — flagged CVE remediation is pending hardening PR (starlette upgrade cross-cuts FastAPI pin); temporary exception is recorded in `.github/security-exceptions.yml` (owner `reviewers-platform-infra`, `expires_on 2026-08-31`), with edge-proxy compensating control documented.

**Release-blocker workflows pending re-validation against post-iter-8 main:**

| Workflow | Maps to | Last known result | Pending action |
|---|---|---|---|
| `.github/workflows/restore-drill.yml` | RB-001 | sqlite-mode green ([run 26215954984](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26215954984)) on `fix/ci-workflows-billing-restore` (pre-iter-8); postgres-minio mode `failure` | Re-trigger against `main` once `alembic-postgres-upgrade` is green |
| `.github/workflows/perf-baseline.yml` | RB-002 | `failure` on pre-iter-8 commits | Re-trigger against `main` once boot is green |
| `.github/workflows/e2e-smoke.yml` | RB-005 | `failure` on pre-iter-8 commits | Re-trigger against `main` once boot is green and frontend `/no-access` regression is verified resolved by iter-8 |

This limitation block exists to make explicit that the release-blocker checkbox states `[ ]` in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` are **not yet stale** — they accurately reflect the absence of post-iter-8 green evidence.

## Test-suite limitations (added 2026-05-26, iter-17b)

The following unit-level tenant-isolation tests were **removed** from `tests/test_tenant_isolation_audit.py` because they had never functioned — both their imports and their session calls were broken since introduction:

| Removed test | Why never worked | Replacement coverage |
|---|---|---|
| `test_audit_log_isolation` | `from app.domains.audit.models import AuditLog` — that path has no `models` submodule; the class lives in `app.models.models`. Also called `.execute(...).scalars().all()` synchronously on an async session. | API-level isolation enforced by `TenantMiddleware` (`backend/app/middleware/tenant.py`); cross-base FK isolation verified by iter-16f schema-naive mirror (PR #572). |
| `test_workflow_events_isolation` | `WorkflowEvent` class does not exist anywhere in the codebase; the `app.domains.workflows` module path also does not exist. The feature was never built. | None at unit level. Per-step workflow event tracking is deferred to v1.1; outbox event isolation is covered indirectly by `OutboxEvent` tenant scoping at the migration / model level. |
| `test_webhook_delivery_isolation` | `from app.domains.integrations.models import Webhook` — module and class names both stale. Real class is `WebhookDelivery` in `app.models.models`. Same sync-on-async session bug. | `WebhookDelivery` carries `tenant_id` via `TenantBaseModel`; isolation is enforced at session-level by `with_tenant_session` search_path setup. |
| `test_outbox_isolation` | `from app.domains.integrations.models import OutboxMessage` — neither module nor class name match reality (`Outbox` in `app.models.models`). Same sync-on-async bug. | `Outbox` carries `tenant_id` via `TenantBaseModel`; same session-level enforcement. |
| `test_notification_isolation` | `from app.domains.notifications.models import Notification` — module path stale; real class lives in `app.models.notifications`. Same sync-on-async bug. | `Notification` carries `tenant_id` via `TenantBaseModel`; integration coverage via `tests/api/test_notifications_calendar_api.py`. |

**Rationale for deletion (not repair):** Each test had two stacked defects — a stale module path and a synchronous `.execute(...)` call on an async session — meaning none of them ever produced a real assertion result; they failed at import or at first DB call. Repairing them in place would require renaming + adding `await` + verifying the seed fixtures actually exist for `tenant-a`/`tenant-b` (none of the broken tests depended on `test_companies_multi_tenant` for `webhook`/`notification`). The cost of rebuilding to working order exceeds the value of unit-level coverage that is already provided at the middleware and model layers, so the v1.0 path is "delete + acknowledge"; proper rebuild is deferred to v1.1.
