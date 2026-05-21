# GAP_REPORT

- **Updated on (UTC):** 2026-05-21
- **Owner:** Stabilization Program (Platform + QA + Product Engineering)
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Release-critical gaps (deduplicated)

| Criterion ID | Gap area | Unified status | Evidence target / current evidence |
|---|---|---|---|
| RC-012 | Restore drill RTO/RPO formal go/no-go criteria | `missing` | Script target: `scripts/restore_drill.py`; test target: `tests/test_health_ready.py`; docs: `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md` |
| RC-005 | Security ownership fallback + escalation SLA codification | `done` | Workflow target: `.github/workflows/ci.yml`; script: `scripts/ci/static_gates.sh`; doc target: `docs/stabilization/security-gates.md`; ownership map target: `.github/CODEOWNERS`; evidence: closed as RB-004 (2026-04-30). |
| RC-006 | Secrets-dependent e2e diagnostics hardening | `missing` | Workflow target: `.github/workflows/e2e-smoke.yml`; test target: `tests/e2e/access/test_access_enforcement_matrix.py`; artifact target: `artifacts/e2e/access-enforcement/*.log` |
| RC-013 | Relational/indexed template scope model migration | `missing` | Workflow target: `.github/workflows/ci.yml`; evidence target in migration tests/scripts |
| RC-014 | Dedicated branch entity separated from current `Site` model | `missing` | Workflow target: `.github/workflows/ci.yml`; evidence target in contract tests + migration scripts |
| RC-015 | Canonical security gate matrix operational closure | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; scripts in `scripts/ci/*`; doc: `docs/stabilization/security-gates.md` |
| RC-016 | Critical-path coverage matrix normalization closure | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; tests/docs in `docs/stabilization/PLAN.md` Block B.1 |

## Post-billing-restore stabilization (added 2026-05-21)

Distinct from the release-critical gaps above, this row tracks the iter-1..8 CI restoration effort. It is **not** a release blocker by itself, but its closure is **prerequisite** to closing RB-001/002/005 (each release-blocker workflow needs a green backend boot to validate its acceptance criteria).

| Tracking ID | Gap area | Unified status | Evidence target / current evidence |
|---|---|---|---|
| Iter-restoration | Post-billing CI rot — main `ci.yml` 3 jobs still red after iter-8 | `partial` | Last failed run [26229962584](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26229962584) on main (pre-iter-8); current in-progress [26235153179](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26235153179) on main (post-iter-8) shows `alembic-postgres-upgrade`, `perf-smoke`, `container-image-scan` already failed. Iter-9 candidate: find remaining migrations needing `postgresql.ENUM(create_type=False)` per pattern in PR #555. See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) section "CI stabilization limitations" for full detail. |

## Resolved but still tracked as references

Closed/non-blocking historical gaps should be tracked in domain docs/tests and must not redefine release-critical statuses outside canonical source.

## Cross-links

- Canonical criteria + checklist: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Release verdict: `RELEASE_READINESS.md`
- Acceptance closure map: `ACCEPTANCE_TEST_MATRIX.md`
- Limitations: `KNOWN_LIMITATIONS.md`
- Stabilization execution plan: `docs/stabilization/PLAN.md`
