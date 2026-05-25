# RELEASE_READINESS

Документ фиксирует **готовность проекта к релизу** (вердикт, RC-критерии, перекрёстные ссылки). Канонический статус блокеров — [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md).

## How to update the release verdict (procedure)

1. **Edit the single source of truth first:** [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md) — RC/RB rows, checklist checkboxes, **Updated on (UTC)**, evidence links.
2. **Sync this file:** `RELEASE_READINESS.md` — align the RC table (`Unified status`), **Launch readiness verdict** (date, `NOT READY` / `READY`, rationale), and **Updated on (UTC)** so it reflects the canonical file.
3. **Root `README.md`:** links to `RELEASE_READINESS.md` and `RELEASE_BLOCKERS_STATUS.md` stay valid; **no README edit** is required for a verdict-only change.
4. **CI:** frontend merge gate already runs `npm --prefix frontend run ci` in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (`frontend-tests` job). For changes under `frontend/**`, run the same locally before release windows when possible.

- **Updated on (UTC):** 2026-05-26
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Release-critical verdict inputs (synced from canonical source)

| Criterion ID | Verdict input | Unified status | Evidence link |
|---|---|---|---|
| RC-001 | Restore drill acceptance closure | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-001, RB-001); evidence: [run 26330050030](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26330050030) (2026-05-23) |
| RC-002 | Performance baseline release-window manifest | `partial` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-002, RB-002); last run [26330051342](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26330051342) `failure` |
| RC-003 | Coverage non-regression gate | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-003, RB-006) |
| RC-004 | Final acceptance overall pass | `partial` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-004, RB-003); `.github/workflows/final-acceptance.yml` added 2026-05-25 (PR #576) but not yet dispatched |
| RC-005 | Security ownership + escalation SLA codification | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-005, RB-004) |
| RC-006 | Secrets-dependent e2e diagnostics hardening | `missing` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-006, RB-005); last run [26330052346](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26330052346) `failure` |

## Launch readiness verdict

- **Verdict date (UTC):** 2026-05-26
- **Verdict:** **NOT READY** (4 of 6 blockers closed; 2 remain — RB-002, RB-005)
- **Release decision checklist:** see `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` → “Release blockers checklist (artifact/workflow mapped)”.
- **Why NOT READY now:** RB-002 (perf baseline) and RB-005 (e2e diagnostics) are not closed. Workflows were re-triggered on 2026-05-23 against post-iter-15h `main` (alembic chain green); `perf-baseline.yml` red on `baseline` job; `e2e-smoke.yml` red on `Minimal smoke (mandatory)`. Failure-class diagnosis is pending (candidates: missing CI secrets for the baseline workload; `/no-access` page rendering regression for the e2e flow per `[[app-level-defects-post-billing]]`).
- **Progress:** RB-001 (restore drill **DONE 2026-05-23**), RB-003 (final acceptance partial — workflow added 2026-05-25, evidence pending), RB-004 (security gates **DONE 2026-04-30**), RB-006 (coverage **DONE**).
- **Path to closure:** (i) diagnose `perf-baseline` failure (likely CI secret / env-var class), (ii) diagnose `e2e-smoke` `/no-access` regression and fix selector or restore heading, (iii) dispatch `final-acceptance.yml` once `e2e-smoke` is green to capture RB-003 evidence.

## Cross-links

- Acceptance evidence map: `ACCEPTANCE_TEST_MATRIX.md`
- Acceptance traceability map: `docs/stabilization/acceptance-traceability.md`
- Limitations affecting release closure: `KNOWN_LIMITATIONS.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization execution tracker: `docs/stabilization/PLAN.md`
