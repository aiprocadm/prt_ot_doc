# RELEASE_READINESS

Документ фиксирует **готовность проекта к релизу** (вердикт, RC-критерии, перекрёстные ссылки). Канонический статус блокеров — [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md).

## How to update the release verdict (procedure)

1. **Edit the single source of truth first:** [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md) — RC/RB rows, checklist checkboxes, **Updated on (UTC)**, evidence links.
2. **Sync this file:** `RELEASE_READINESS.md` — align the RC table (`Unified status`), **Launch readiness verdict** (date, `NOT READY` / `READY`, rationale), and **Updated on (UTC)** so it reflects the canonical file.
3. **Root `README.md`:** links to `RELEASE_READINESS.md` and `RELEASE_BLOCKERS_STATUS.md` stay valid; **no README edit** is required for a verdict-only change.
4. **CI:** frontend merge gate already runs `npm --prefix frontend run ci` in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (`frontend-tests` job). For changes under `frontend/**`, run the same locally before release windows when possible.

- **Updated on (UTC):** 2026-05-21
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Release-critical verdict inputs (synced from canonical source)

| Criterion ID | Verdict input | Unified status | Evidence link |
|---|---|---|---|
| RC-001 | Restore drill acceptance closure | `partial` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-001, RB-001) |
| RC-002 | Performance baseline release-window manifest | `partial` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-002, RB-002) |
| RC-003 | Coverage non-regression gate | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-003, RB-006) |
| RC-004 | Final acceptance overall pass | `partial` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-004, RB-003) |
| RC-005 | Security ownership + escalation SLA codification | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-005, RB-004) |
| RC-006 | Secrets-dependent e2e diagnostics hardening | `missing` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-006, RB-005) |

## Launch readiness verdict

- **Verdict date (UTC):** 2026-05-21
- **Verdict:** **NOT READY** (3 of 6 blockers closed; 3 remain)
- **Release decision checklist:** see `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` → “Release blockers checklist (artifact/workflow mapped)”.
- **Why NOT READY now:** RB-001 (restore drill), RB-002 (perf baseline), RB-005 (e2e diagnostics) are not closed. As of 2026-05-21 verdict refresh, **no green workflow artifact exists for any of the three against post-iter-8 `main`**; see "Recent stabilization activity" section of `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` for the iter-1..8 timeline and current red-state on `main` CI (3 jobs still failing — `perf-smoke`, `alembic-postgres-upgrade`, `container-image-scan`).
- **Progress:** RB-003 (final acceptance partial), RB-004 (security gates **DONE as of 2026-04-30**), RB-006 (coverage **DONE**).
- **Path to closure:** iter-9 to address remaining `alembic-postgres-upgrade` failures (additional migrations likely need `postgresql.ENUM(create_type=False)` per pattern established in PR #555), then trigger and verify `restore-drill.yml` / `perf-baseline.yml` / `e2e-smoke.yml` against green `main`.

## Cross-links

- Acceptance evidence map: `ACCEPTANCE_TEST_MATRIX.md`
- Acceptance traceability map: `docs/stabilization/acceptance-traceability.md`
- Limitations affecting release closure: `KNOWN_LIMITATIONS.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization execution tracker: `docs/stabilization/PLAN.md`
