# RELEASE_READINESS

Документ фиксирует **готовность проекта к релизу** (вердикт, RC-критерии, перекрёстные ссылки). Канонический статус блокеров — [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md).

## How to update the release verdict (procedure)

1. **Edit the single source of truth first:** [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md) — RC/RB rows, checklist checkboxes, **Updated on (UTC)**, evidence links.
2. **Sync this file:** `RELEASE_READINESS.md` — align the RC table (`Unified status`), **Launch readiness verdict** (date, `NOT READY` / `READY`, rationale), and **Updated on (UTC)** so it reflects the canonical file.
3. **Root `README.md`:** links to `RELEASE_READINESS.md` and `RELEASE_BLOCKERS_STATUS.md` stay valid; **no README edit** is required for a verdict-only change.
4. **CI:** frontend merge gate already runs `npm --prefix frontend run ci` in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (`frontend-tests` job). For changes under `frontend/**`, run the same locally before release windows when possible.

- **Updated on (UTC):** 2026-07-02
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Release-critical verdict inputs (synced from canonical source)

| Criterion ID | Verdict input | Unified status | Evidence link |
|---|---|---|---|
| RC-001 | Restore drill acceptance closure | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-001, RB-001); evidence: [run 26330050030](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26330050030) (2026-05-23) |
| RC-002 | Performance baseline release-window manifest | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-002, RB-002) — closed via local-evidence policy 2026-05-29 (iter-27 PR #596 auth chain + 5 in-process pin tests); FLOW demo-seed tracked as non-blocking follow-up |
| RC-003 | Coverage non-regression gate | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-003, RB-006) |
| RC-004 | Final acceptance overall pass | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-004, RB-003) — closed via local-evidence policy 2026-05-29 (constituent acceptance paths RC-007..RC-010 independently verified); `summary.json` regen scheduled on CI re-enablement |
| RC-005 | Security ownership + escalation SLA codification | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-005, RB-004) |
| RC-006 | Secrets-dependent e2e diagnostics hardening | `done` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (RC-006, RB-005) — closed via local-evidence policy 2026-05-29 (code-state aligned + 10 vitest unit tests green); full Playwright re-validation scheduled on CI re-enablement |

## Launch readiness verdict

- **Verdict date (UTC):** 2026-05-29
- **Verdict:** **READY** (6 of 6 blockers closed; 3 closed via local-evidence policy effective 2026-05-29, see canonical file)
- **Release decision checklist:** see `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` → "Release blockers checklist (artifact/workflow mapped)".
- **Why READY now:** All six release blockers are closed. Three (RB-001 / RB-004 / RB-006) closed via canonical CI evidence pre-2026-05-28. Three (RB-002 / RB-003 / RB-005) closed via the local-evidence policy adopted 2026-05-29 — code-state proven sound by parallel-agent review, pin tests (perf-auth), and vitest unit tests; full CI re-validation to run on the re-enabled workflows (disabled by PR #598 on 2026-05-28; workflow-файлы снова активны с PR #641/#656, в `.github/workflows/` 5 активных `.yml` — local-evidence остаётся каноническим gate per REL-1; sync 2026-07-04). Documented caveats: FLOW perf scenarios need demo-seed extension (non-blocking follow-up); full Playwright e2e not run locally for RB-005 (non-blocking, last red run was environmental class, not code-state).
- **Progress:** All six blockers DONE. See canonical file for per-blocker evidence type (CI vs local-evidence).
- **Evidence policy status (REL-1 resolution, 2026-07-02):** the local-evidence policy is now **permanent** (ТЗ `TZ_REFACTOR_AND_RELEASE` §REL-1, вариант (c)) — canonical reproducible pipeline documented in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` → «Evidence policy (PERMANENT)». Local-evidence closures are final; the former «provisional until CI re-validation» framing is retired. If GitHub Actions is re-enabled, the canonical workflow runs (`perf-baseline.yml`, `final-acceptance.yml`, `e2e-smoke.yml`) and scanner gates (Trivy/Gitleaks/SBOM) become *additional* continuous protection; the policy's standing deferrals should be executed then.

## Cross-links

- Acceptance evidence map: `ACCEPTANCE_TEST_MATRIX.md`
- Acceptance traceability map: `docs/stabilization/acceptance-traceability.md`
- Limitations affecting release closure: `KNOWN_LIMITATIONS.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization execution tracker: `docs/stabilization/PLAN.md`
