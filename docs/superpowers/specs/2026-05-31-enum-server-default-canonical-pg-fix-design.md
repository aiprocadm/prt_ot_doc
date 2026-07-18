# Design — fix iter38 enum `server_default` case-mismatch (canonical PG boot-blocker)

- **Date:** 2026-05-31
- **Branch:** `fix/iter38-enum-server-default-case` (off `main` @ `0d53f46`)
- **Status:** design approved (brainstorming) → pending implementation plan
- **Driver:** brainstorming → writing-plans → executing-plans (TDD against live PG16)
- **Release context:** target = **canonical CI-green** (user choice). This slice removes the single hard gate that blocks backend boot on Postgres, which in turn blocks every release-blocker workflow re-validation (RB-002/003/005) and the coverage bootstrap (`TZ-6.3-V11-01`). See `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` and `KNOWN_LIMITATIONS.md` (CI-stabilization section).

## Problem (reproduced canonically, not inferred)

`alembic upgrade heads` against a **fresh Postgres 16** fails:

```
File: backend/app/migrations/versions/20260529_iter38_server_default_cohort_c.py, line ~101
SQL:  ALTER TABLE approval_processes ALTER COLUMN status SET DEFAULT 'PENDING'
Err:  asyncpg.exceptions.InvalidTextRepresentationError:
      invalid input value for enum approvalprocessstatus: "PENDING"
```

Reproduction (2026-05-31, local): throwaway DB `alembic_verify` on the running `postgres:16` container (`postgres/postgres@localhost:5432`), `DATABASE_URL=postgresql+asyncpg://…/alembic_verify`, `.venv` (Py3.13.7) + alembic 1.13.3 + asyncpg. ~80 migrations apply, then iter38 aborts. env.py wraps the **entire** upgrade in one transaction (`async with connectable.begin()`), so the failure rolls **everything** back → DB ends empty → **backend cannot boot on PG at all** (all-or-nothing, not partial degradation).

> The older `DuplicateObjectError` that `KNOWN_LIMITATIONS.md` (2026-05-21) blames was already fixed (migration `8d2c1a6c5e24` correctly uses `create_type=False` + `.create(checkfirst=True)`). The current boot-blocker is a **different, newer** bug introduced by the iter38 server_default-parity cohort. The docs were stale; the reproduction is the source of truth.

## Root cause

iter38 ("Subset C parity cohort") adds `server_default` to 33 enum-typed columns. Its docstring assumes SQLAlchemy stores the enum **member name** (UPPER_CASE) on PG, so it writes `server_default="PENDING"`, `"OPEN"`, `"QUEUED"`, etc. But this project configures many enums with `values_callable` to store the lowercase `.value` — so the PG type `approvalprocessstatus` has labels `[pending,in_progress,approved,rejected,canceled,expired]`. `'PENDING'` is not a valid label → `InvalidTextRepresentationError`.

**Storage is inconsistent across enums** (verified by `pg_enum` introspection of the iter37 DB state):

| Stores UPPER_CASE names (default already valid) | Stores lowercase values (default invalid) |
|---|---|
| `equipmentstatus=[ACTIVE,IN_SERVICE,DECOMMISSIONED]` | `approvalprocessstatus=[pending,…]` |
| `idempotencystatus=[PENDING,SUCCEEDED,FAILED]` | `approvaltaskstatus=[open,done,canceled,expired]` |
| `incidentseverity=[LOW,MEDIUM,HIGH]` | `attestationstatus=[active,expired,revoked]` |
| `templateversionstatus=[…,UPLOADED,…]` | `edoenvelopestatus=[queued,sent,…]` |

So the fix is **per-column**, matched to each enum's real labels — **not** a blanket lowercase conversion. Some columns may map to plain `String`/VARCHAR (not native enum), where any string is accepted (e.g. `approval_instances.status` did not fail) — those need no change.

## Decision — Approach A: correct each `server_default` to a valid enum label

Change only the invalid literals in iter38 to a label that exists in the corresponding enum (e.g. `"PENDING"→"pending"`, `"OPEN"→"open"`, `"QUEUED"→"queued"`); leave already-valid UPPER_CASE ones and `tenant.kind="customer"` untouched. Downgrade (`server_default=None`) is unaffected.

**Why A over B (drop the enum defaults entirely):** iter38's purpose — DB-level defaults matching the ORM `default=` — is load-bearing for raw-SQL insert paths (perf-baseline `COPY`, restore-drill SQL dumps; i.e. RB-001/RB-002). Dropping the defaults reverts that and re-opens the `scripts/audit/server_default_parity.py` gate (drift 0 → 33), merely moving the red from one check to another. A keeps both gates satisfiable.

**Why not `sa.text("'value'::enumname")`:** PG-only syntax; iter38 deliberately used dialect-portable plain strings (SQLite stores SA Enum as VARCHAR). Keep that property — plain lowercase string relies on PG's implicit assignment-context text→enum cast, same as the `billing_core` precedent the docstring itself cites.

## The exact corrections — derived, not guessed

Authoritative source is `pg_enum`, not naming. For each of the 33 iter38 `alter_column` targets:
1. Read the column's real type: `information_schema.columns.udt_name` against the iter37 DB state.
2. If the type is an enum, take its labels from `pg_enum`. If `server_default` literal ∈ labels → leave as-is. Else → replace with the matching label (case-corrected; same logical member).
3. If the type is not an enum (VARCHAR) → leave as-is.

The implementation plan will produce the column→type→corrected-literal table from live introspection (a deterministic query), so every change is backed by a DB fact.

## Verification — live PG16 is the oracle (canonical-equivalent, local)

TDD loop, fully local, before CI is touched:
1. **Red:** recreate fresh `alembic_verify`; `alembic upgrade heads` fails at the first invalid default. (Already observed.)
2. **Green-by-increment:** correct the failing column → re-run → advance to the next failure → repeat.
3. **Done:** `alembic upgrade heads` exits 0 through all heads on a fresh DB. That is canonical-equivalent proof the boot-blocker is gone.
4. **Idempotency/cleanliness:** confirm `alembic downgrade` of iter38 + re-`upgrade` is clean; drop the throwaway DB at the end.

Caveat (declared): host Python is 3.13.7, canonical is 3.12.12. The bug is **server-side PG DDL**, so Python version is irrelevant to it; the definitive 3.12.12 run still happens in CI on re-enable. Recorded per the local-evidence policy.

## Guard against regression

- **Primary (already exists):** the disabled CI job `alembic-postgres-upgrade` *is* the permanent guard — this fix turns it green; it stays green thereafter.
- **Added (this slice):** a focused test asserting that every enum-typed `server_default` literal in the migrations dir is a valid label of its enum (reads ORM enum `.value`s; app-light, no full route import). Catches a recurrence before CI returns. Exact form decided in the plan (must avoid the static-analysis blind spots in `[[audit-static-analysis-blindspots]]` — prefer reading real enum values over regex heuristics).

## Scope boundary (enum-slice first — user choice)

**In scope:** iter38 corrections; live-PG canonical verification; guard test; update `KNOWN_LIMITATIONS.md`/`RELEASE_BLOCKERS_STATUS.md` notes to reflect the real (now-fixed) blocker; stage CI workflows for re-enable (rename remains the user's operational flip).

**Out of scope (each its own follow-up plan once backend boots):** RB-002 perf-baseline re-validation (branch `chore/rb-002-flow-scenarios-trim` already exists), RB-003 final-acceptance regen, RB-005 e2e-smoke environmental diagnosis, coverage-floor bootstrap → `TZ-6.3-V11-01` → done, `container-image-scan` CVE (temp exception until 2026-08-31).

## Risks / open questions

- **Other latent boot-blockers downstream of iter38?** Unknown until the upgrade goes fully green — the single-transaction rollback hides anything after the first failure. The loop surfaces them one at a time; if a non-enum failure appears, re-assess scope.
- **iter37 safe?** Yes — Subset A/B are int/bool/string defaults; upgrade to iter37 verified green (exit 0).
- **ORM↔DB default consistency:** after the fix, the DB `server_default` should equal what the ORM persists. The plan cross-checks a sample against ORM `default=` to ensure parity is real, not just syntactically valid.
