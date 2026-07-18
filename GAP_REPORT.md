# GAP_REPORT

- **Updated on (UTC):** 2026-06-30
- **Owner:** Stabilization Program (Platform + QA + Product Engineering)
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Release-critical gaps (deduplicated)

| Criterion ID | Gap area | Unified status | Evidence target / current evidence |
|---|---|---|---|
| RC-012 | Restore drill RTO/RPO formal go/no-go criteria | `done` | `scripts/restore_drill.py::evaluate_rto_rpo` emits a `go_no_go` block (measured RTO/RPO vs threshold + `decision`), folded into `success`; thresholds default to ТЗ vNext §31.6 (RTO 4h / RPO 24h), overridable via `--rto/rpo-threshold-seconds` / env; doc `docs/stabilization/restore-drill.md` (Acceptance criteria + "RTO/RPO go/no-go" §); tests `tests/test_restore_drill_go_no_go.py` (7, green Py3.12 2026-06-29). Honest caveat: measured RPO = rehearsal seed→backup lag (lower bound), stated in `go_no_go.rpo_basis`. |
| RC-005 | Security ownership fallback + escalation SLA codification | `done` | Workflow target: `.github/workflows/ci.yml`; script: `scripts/ci/static_gates.sh`; doc target: `docs/stabilization/security-gates.md`; ownership map target: `.github/CODEOWNERS`; evidence: closed as RB-004 (2026-04-30). |
| RC-006 | Secrets-dependent e2e diagnostics hardening | `done` | Closed via local-evidence policy 2026-05-29 (see `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` RB-005). Workflow target: `.github/workflows/e2e-smoke.yml`; test target: `tests/e2e/access/test_access_enforcement_matrix.py`; artifact target: `artifacts/e2e/access-enforcement/*.log` (regen scheduled on CI re-enablement) |
| RC-013 | Relational/indexed template scope model migration | `done` | Model: `Template.scope_level` / `scope_company_id` / `scope_site_id` + index `ix_template_scope_level_company_site` (migration `20260416_next68_template_scope_normalization`, backfills from JSON). Reader cutover (2026-06-29): `app/api/routes/documents.py::_normalize_scope_level` / `_scope_target_ids` now read the relational columns (JSON fallback for un-backfilled rows); writer dedup in `app/api/v1/router.py::patch_template` (double `scope_level` assignment removed). Tests `tests/test_template_scope_relational_reads.py` (6) + existing `tests/test_template_catalog_scope.py` green. `metadata_json["scope"]` retained as compat mirror; DB-level scope pre-filter in the resolve query deferred (non-blocking — un-backfilled-row safety). |
| RC-014 | Dedicated branch entity separated from current `Site` model | `done` | Closed 2026-07-02 (local-evidence policy). Model: `app/models/master_data.py::Branch` (company-scoped филиал: vNext-иерархия «компании → филиалы → объекты»; VARCHAR `status` — вне enum-parity класса) + additive `Site.branch_id` (app-level link, no DB FK — wa02 precedent; целостность в API). Migration `20260702_br01_branch_entity` (create `branch` + `site.branch_id`+index; honest downgrade; validated on PG16 gate). CRUD `/api/v1/branches` + site-link validation (tenant + company match). Contract tests `tests/test_branches_api.py` (5: CRUD roundtrip, cross-tenant isolation, link/unlink, company mismatch → 400, ghost branch → 404); AST drift-audit green (59). OpenAPI baseline re-snapped 803/644→808/648 (sanctioned additive exception per ТЗ RC-013/RC-014) |
| RC-015 | Canonical security gate matrix operational closure | `done` | Closed 2026-07-02 (permanent local-evidence policy, REL-1(c)). Script gates + SAST + static gates green locally; scanner gates (Trivy/Gitleaks/SBOM) = documented standing deferrals. Evidence detail: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` RC-015; doc: `docs/stabilization/security-gates.md` |
| RC-016 | Critical-path coverage matrix normalization closure | `done` | Closed 2026-07-02 (permanent local-evidence policy, REL-1(c)). Block B.1 backend suite 14 passed locally; Playwright smoke = standing deferral (RB-005 precedent). Evidence detail: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` RC-016; docs: `docs/stabilization/coverage.md` |

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
