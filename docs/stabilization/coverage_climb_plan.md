# Coverage climb plan — core/domain/services → 85% (TZ-6.3-V11-01)

**Status:** ✅ **active.** W0 (CI re-enable) is done; the scoped gate is wired
into the **live** `.github/workflows/ci.yml` (`Scoped coverage climb gate` step)
and ran green on the canonical run **27508869071** (2026-06-14, Py3.12.12, 3138
tests). Per-scope floors are **bootstrapped from that run's real
`coverage.json`** (see Bootstrap below) — no longer conservative seeds. The
ratchet now holds the real line: any PR that drops a scope below its floor fails
CI. 85% line remains the North-Star to climb toward.

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

## Baseline — bootstrapped 2026-06-14 (canonical, direct per-scope)

The earlier 2026-04-19 themed proxy (overall 47.0% line / 36.0% branch) has been
**superseded** by direct per-scope measurement from the first canonical CI run
after W0 (run **27508869071**, Py3.12.12, 3138 tests):

| Scope | line % (measured) | branch % (measured) | statements | floor (line/branch) | gap to 85% |
|---|---|---|---|---|---|
| core | 82.83 | 69.33 | 2469 | 81.0 / 68.0 | +2.17 |
| domain | 75.18 | 59.03 | 2172 | 74.0 / 58.0 | +9.82 |
| services | 79.63 | 65.92 | 6231 | 78.0 / 64.0 | +5.37 |

Floors are `floor(measured)` minus a ~1pp jitter margin (whole-percent,
~1.0–1.9pp headroom) so the ratchet locks in the real gain without false-failing
on run-to-run coverage jitter. The actual numbers came in **far above** the old
conservative seeds (core 40 / domain 35 / services 25 line) — the suite was
already near the North-Star.

## Bootstrap — DONE (2026-06-14, post-W0)

1. ✅ Re-enable CI (W0); the backend coverage job produced `artifacts/coverage.json`
   on run 27508869071.
2. ✅ Read the actual per-scope line/branch from that report and wrote them into
   `docs/stabilization/scoped_coverage_baseline.json` as the real floors (above).
3. ✅ The ratchet now holds the line; every PR that lowers a scope below its floor
   fails `scripts/ci/check_scoped_coverage.py`.

## Climb milestones (47% → 85%)

Attack the lowest-coverage scope first — it has the most untested surface per
test written, so it moves the overall number fastest.

| Milestone | Focus | Target | Status (2026-06-14 canonical) |
|---|---|---|---|
| M1 | `services` (outbox/events/idempotency/audit) | services ≥ 55% line | ✅ met (79.63%) |
| M2 | `domain` (risk, ppe, prescriptions, packs) — pure functions first | domain ≥ 65% line | ✅ met (75.18%) |
| M3 | `core` (security/tenancy/rbac) — close the gaps | core ≥ 80% line | ✅ met (82.83%) |
| M4 | All scopes converge | each scope ≥ 85% line (North Star) | climbing — domain +9.82, services +5.37, core +2.17 |

The 47%→85% framing was set against the 2026-04-19 proxy; the canonical
per-scope measurement landed M1–M3 already met. Remaining work is **M4** —
close the last few points per scope (domain has the largest gap, attack it
first). After each gain, raise the corresponding floor(s) in the baseline so the
ratchet locks it in. Prefer **app-free unit tests** (pure functions in
`core`/`domain`) — they are fast, deterministic, and runnable even on the
Py3.13/Win local box where the full app-booting suite is flaky.

## Mechanism

- **Gate script:** `scripts/ci/check_scoped_coverage.py` — pure `evaluate()`
  core (ratchet + gap-to-target) + CLI. Unit-tested with synthetic
  `coverage.json` (`backend/tests/test_check_scoped_coverage.py`), so the logic
  is verified without a live coverage run.
- **Floors:** `docs/stabilization/scoped_coverage_baseline.json`.
- **CI:** a `Scoped coverage climb gate` step in the live `.github/workflows/ci.yml`
  runs the script after the backend coverage job; non-zero exit fails the build.
- **Run locally** (once you have a `coverage.json`):
  `python scripts/ci/check_scoped_coverage.py --coverage-json artifacts/coverage.json`

## Relationship to the existing whole-app baseline

This scoped gate **complements** `scripts/ci/check_backend_coverage_baseline.py`
(whole-app `backend/app` ratchet). The whole-app check guards the overall
number; this scoped check focuses the climb on the three packages `TZ-6.3-V11-01`
calls out and tracks their distance to 85%.
