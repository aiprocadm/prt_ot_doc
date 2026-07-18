# Merge Playbook — Sessions 86–91 (iter-39/40/41/42/43 + RB-002 trim)

**Status:** 6 in-flight branches, all from `main@093959b`. Integration validation
completed on `validate/all-six-branches-integration` (commit `855385b`).

**Validation results:**
- column_drift_lite: **0 business-drift + 0 critical-absent**
- server_default_parity: **0/0**
- version_column_drift: **0/0** (was 0/2 pre-iter-42; incident_log + incident_person now created)
- Combined test suite (12 files, iter-29..43 + audits): **517/517 pass**

## Branches summary

| # | Branch | Commit | LOC | Migration? | Conflict on report? |
|---|---|---|---|---|---|
| 1 | `fix/iter-39-audit-batch-alter-dynamic-table-resolution` | `e6bf3de` | +281 | No (audit-only) | First merge — no conflict |
| 2 | `fix/iter-40-training-certificates-legacy-cols` | `858beb6` | +410 | Yes (`iter40_tc_legacy_cols`, parent: `iter-38`) | Yes (after iter-39) |
| 3 | `fix/iter-41-journalentry-concept-resolution` | `2945b15` | +535 | Yes (`iter41_journalentry_concept`, parent: `iter-38`) | Yes |
| 4 | `fix/iter-42-incident-family-cohort` | `a40020e` | +1162 | Yes (`iter42_incident_family`, parent: `iter-38`) | Yes (also conflict on `test_audit_column_drift_lite.py` — flipped Session-80 test) |
| 5 | `fix/iter-43-incident-status-enum-type-parity` | `2cb158d` | +360 | Yes (`iter43_incident_status_enum`, parent: `iter-38`) | Yes |
| 6 | `chore/rb-002-flow-scenarios-trim` | `aa3e9a8` | +259/-144 | No | Yes |

## Recommended merge order

```
1. iter-39 → main         (no migration, no conflict)
2. iter-40 → main         (alembic head: iter-40)
3. iter-41 → main         (alembic heads: iter-40, iter-41)  → run alembic merge heads
4. iter-42 → main         (heads: <merged>, iter-42)         → run alembic merge heads
5. iter-43 → main         (heads: <merged>, iter-43)         → run alembic merge heads
6. RB-002 trim → main     (no migration, no conflict)
7. (optional) test-relax  (3 tests, on validation branch as `855385b`)
```

After 3+5 merges with `alembic merge heads`, history has 3 no-op merge migrations.

## Conflict resolution recipe

**Every merge after the first triggers one conflict on `AI_IMPLEMENTATION_REPORT.md`**
(both branches prepended a new handoff at line 3).

Resolution: keep both handoffs, in chronological-descending order
(higher session # above lower). Python one-liner:

```bash
py -3 -c "
import re
from pathlib import Path
path = Path('AI_IMPLEMENTATION_REPORT.md')
text = path.read_text(encoding='utf-8')
pattern = re.compile(r'<<<<<<<\\s*HEAD\\s*\\n(.*?)\\n=======\\s*\\n(.*?)\\n>>>>>>>[^\\n]*\\n', re.DOTALL)
resolved = pattern.sub(lambda m: m.group(2) + '\\n' + m.group(1) + '\\n', text)
assert '<<<<<<<' not in resolved
path.write_text(resolved, encoding='utf-8')
print(f'Resolved {len(pattern.findall(text))} conflict regions')
"
git add AI_IMPLEMENTATION_REPORT.md
git commit --no-edit
```

**iter-42 also conflicts on `backend/tests/test_audit_column_drift_lite.py`**
(flipped Session-80 test `test_real_codebase_incident_log_is_critical_absent` → `_no_longer_critical_absent`). Auto-merge succeeds; no manual resolution needed.

## Alembic merge heads commands

After each merge of an iter-4X branch beyond the first, run:

```bash
alembic -c backend/app/migrations/alembic.ini merge heads -m "merge iter-X + iter-Y heads"
git add backend/app/migrations/versions/*_merge*.py
git commit -m "chore(migrations): merge heads after iter-X + iter-Y"
```

Three merges expected total (after iter-41, after iter-42, after iter-43).

## Post-merge audit checks

After all 6 branches land on main:

```bash
py -3 scripts/audit/column_drift_lite.py
# Expect: 0 business-drift + 0 critical-absent

py -3 scripts/audit/server_default_parity.py
# Expect: 0 cols / 0 tables

py -3 scripts/audit/version_column_drift.py
# Expect: 0 missing version + 0 critical
```

All three audits should report 0/0 — the entire drift defect class (across all 3 lightweight audits) is closed.

## Pre-deploy verifications

Three of the migration-bearing branches make destructive or assumption-based changes:

| Branch | Concern | Pre-deploy command |
|---|---|---|
| iter-41 | drop_table('journalentry') | `SELECT count(*) FROM journalentry` (assumed empty; if not, dump-and-decide) |
| iter-42 | add NOT NULL FK on incident.company_id, site_id (no backfill) | `SELECT count(*) FROM incident` (must be 0 or migration fails) |
| iter-43 | ALTER incident.status type with `status::text::incidentstatus` cast | `SELECT DISTINCT status FROM incident` (values must be in {REPORTED, INVESTIGATING, ACTIONS, CLOSED, CANCELLED}) |

iter-39, iter-40, RB-002 trim have no destructive concerns.

## Closed-loop test relaxations

The validation branch found 3 tests that need relaxation under integrated state:

- `test_audit_column_drift_lite.py::test_real_codebase_business_drift_count_drops_to_five_after_iter39`
- `test_iter40_training_certificates_legacy_cols.py::test_audit_drift_count_drops_to_four_after_iter40`
- `test_iter41_journalentry_concept_resolution.py::test_audit_drift_journalentry_cleared_after_iter41`

Each test was correct in isolation (assumed OTHER iters hadn't landed) but fails when ALL drift is closed (`drift_tables == empty set` violates the equality / subset checks for design-blocked tables that have now been resolved).

Two ways to apply:
- **(a) Pre-merge fix** — apply relaxations to iter-39/40/41 branches BEFORE merging. Cleaner history.
- **(b) Post-merge fix** — apply as a follow-up commit after the integration is complete. Validation branch already has the fix as commit `855385b`.

## Validation branch artifacts

`validate/all-six-branches-integration` contains the integrated state and can be used as a reference:

```bash
git log --oneline validate/all-six-branches-integration
# 855385b test(audit): relax intermediate-state assertions in iter-39/40/41 closed-loop tests
# 9fa72ef merge RB-002 trim (Session 91 — perf nightly_baseline pure-GET)
# df06801 merge iter-43 (Session 90 — incident.status enum type parity)
# c4b1bab merge iter-42 (Session 89 — incident family cohort + 5 enums)
# 3e13c21 merge iter-41 (Session 88 — journalentry concept resolution)
# 77f4684 merge iter-40 (Session 87 — training_certificates legacy cols)
# f25b972 merge iter-39 (Session 86 — audit blindspot fix: dynamic batch_alter_table)
# ... main history ...
```

This branch is local-only (not pushed). Treat as a reference for the merged shape — discard once main reaches the same state via individual PR merges.

## Caveats not addressed by this validation

- **Multi-head alembic state pre-existing.** The repo already has 16 non-iter heads (`20250218_*`, `20250322_*`, etc.) that are orphan terminal revisions. Not introduced by this session's work. Diagnostic-only.
- **No PG-side validation.** Win+Py3.13 conftest hang prevented running migrations against a real PG instance. Pre-deploy verifications (above) are the operational mitigation.
- **CI is off.** Per [[ci-disabled-actions-off]]. Local-evidence policy applies.
- **6 in-flight branches not pushed.** All commits are local. Push when ready to open PRs.
