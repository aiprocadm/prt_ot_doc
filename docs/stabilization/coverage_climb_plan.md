# Coverage climb plan — core/domain/services → 85% (TZ-6.3-V11-01)

**Status:** tooling + plan shipped; the gate **activates with W0** (CI re-enable).
The scoped gate is wired into `.github/workflows/ci.yml.disabled` and runs only
once CI is turned back on.

## Why a climb plan, not a hard 85% gate

The last full coverage measurement (CI, **2026-04-19**) recorded **47.0% line /
36.0% branch** overall — far below 85%. A hard ≥85% gate would fail every build
immediately and block all merges. So 85% is the **North-Star target**, and the
enforced mechanism is a **ratchet**: coverage may not drop below a recorded
per-scope floor, and the floor is raised as tests land. The gate reports each
scope's remaining gap to 85% so progress is visible every run.

## Scope

Three packages, per `TZ-6.3-V11-01`:

| Scope | Path | Why it matters |
|---|---|---|
| `core` | `backend/app/core/` | security, tenancy, RBAC/ABAC, config — the trust boundary |
| `domain` | `backend/app/domains/` | business rules (risk, ppe, prescriptions, packs, …) |
| `services` | `backend/app/services/` | outbox, events, idempotency, audit — cross-cutting infra |

## Baseline (2026-04-19, themed proxy)

The 2026-04-19 baseline is recorded by **theme**, which overlaps the scopes:

| Theme (proxy) | line % | branch % | Overlaps scope |
|---|---|---|---|
| tenancy | 72.2 | 57.8 | core |
| rbac_abac | 66.2 | 46.3 | core |
| auth | 65.5 | 49.4 | core |
| files | 55.7 | 39.6 | domain |
| jobs_outbox | 31.9 | 31.5 | services |
| **overall** | **47.0** | **36.0** | — |

Per-scope numbers are not yet measured directly; the seed floors in
`scoped_coverage_baseline.json` are deliberately **conservative** (core 40 /
domain 35 / services 25 line) so the ratchet does not false-fail on the first
real run.

## Bootstrap (first CI run after W0)

1. Re-enable CI (W0); the backend coverage job produces `artifacts/coverage.json`.
2. Read the actual per-scope line/branch from the report and write them into
   `docs/stabilization/scoped_coverage_baseline.json` as the real floors.
3. From then on the ratchet holds the line; every PR that lowers a scope below
   its floor fails `scripts/ci/check_scoped_coverage.py`.

## Climb milestones (47% → 85%)

Attack the lowest-coverage scope first — it has the most untested surface per
test written, so it moves the overall number fastest.

| Milestone | Focus | Target |
|---|---|---|
| M1 | `services` (outbox/events/idempotency/audit) — lift from ~32% proxy | services ≥ 55% line |
| M2 | `domain` (risk, ppe, prescriptions, packs) — pure functions first | domain ≥ 65% line |
| M3 | `core` (security/tenancy/rbac) — already 65–72%; close the gaps | core ≥ 80% line |
| M4 | All scopes converge | each scope ≥ 85% line (North Star) |

After each milestone, raise the corresponding floor(s) in the baseline so the
ratchet locks in the gain. Prefer **app-free unit tests** (pure functions in
`core`/`domain`) — they are fast, deterministic, and runnable even on the
Py3.13/Win local box where the full app-booting suite is flaky.

## Mechanism

- **Gate script:** `scripts/ci/check_scoped_coverage.py` — pure `evaluate()`
  core (ratchet + gap-to-target) + CLI. Unit-tested with synthetic
  `coverage.json` (`backend/tests/test_check_scoped_coverage.py`), so the logic
  is verified without a live coverage run.
- **Floors:** `docs/stabilization/scoped_coverage_baseline.json`.
- **CI:** a `Scoped coverage climb gate` step in `ci.yml(.disabled)` runs the
  script after the backend coverage job; non-zero exit fails the build.
- **Run locally** (once you have a `coverage.json`):
  `python scripts/ci/check_scoped_coverage.py --coverage-json artifacts/coverage.json`

## Relationship to the existing whole-app baseline

This scoped gate **complements** `scripts/ci/check_backend_coverage_baseline.py`
(whole-app `backend/app` ratchet). The whole-app check guards the overall
number; this scoped check focuses the climb on the three packages `TZ-6.3-V11-01`
calls out and tracks their distance to 85%.
