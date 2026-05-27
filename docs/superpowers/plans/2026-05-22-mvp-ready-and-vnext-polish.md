# MVP READY + vNext Phase 5-9 Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> This is a **master plan**. Phase 0 is fully detailed (TDD-step granularity, immediately executable). Phase 1 has concrete task scope but defers per-feature TDD steps to per-task sub-plans (created on entry to each task). Phase 2 is a roadmap; each task spawns its own sub-plan when reached.

**Goal:** Take the project from current state (3 of 6 release blockers open; `alembic-postgres-upgrade` CI red on iter-13 verdict pending) to **MVP READY** verdict, then close remaining MVP `[v1.1]/[v1.2]` partials, then complete vNext Phase 5-9 polish follow-ups already named in recent handoffs.

**Architecture:** Three sequential phases. Phase 0 unblocks the binary go/no-go (RB-001/002/005). Phase 1 closes the 3 remaining matrix partials (PPE warehouse, prescriptions lifecycle, coverage gate). Phase 2 finishes the named polish follow-ups from Phase 5-9 handoffs (Cache-Control uniformity, remaining list-endpoint ETag, slow-query identification, Site Card UI, Operational Dashboard frontend, notifications orchestration).

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / asyncpg / pytest / React 18+ / TS strict / Vite / Playwright; GitHub Actions (CI matrix); MinIO / LibreOffice (restore-drill dependencies).

**Canonical references (do not re-derive):**
- TZ: [`docs/spec/TZ_FULL_UNIFIED.md`](../../spec/TZ_FULL_UNIFIED.md)
- Coverage matrix: [`docs/audit/TZ_COVERAGE_MATRIX.md`](../../audit/TZ_COVERAGE_MATRIX.md)
- Release blockers: [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](../../stabilization/RELEASE_BLOCKERS_STATUS.md)
- Handoff log: [`AI_IMPLEMENTATION_REPORT.md`](../../../AI_IMPLEMENTATION_REPORT.md)
- Production rules to obey for every task: TZ §E (ARCHITECTURE_RULES, ENGINEERING_RULES, PRODUCT_UX_RULES, SIX_QUESTIONS)

---

## File Structure (overview)

This plan touches three areas. Files are listed once; later tasks may modify them.

**Backend — migrations & CI safety (Phase 0):**
- Create: `tests/test_migrations_comprehensive_safety.py` (new AST sweep pin-test, ~600-800 LOC, supersedes/extends existing two pin-tests).
- Modify (Phase 0 fixes, surfaced by sweep): individual files under `backend/app/migrations/versions/*.py` — exact list determined by sweep run; expected 5-15 files based on iter-9..13 historical hit rate.
- Modify: `.github/workflows/restore-drill.yml` (add LibreOffice install step, pin minio image).
- Modify: `scripts/restore_drill.py` (relax object-mismatch verifier OR keep strict and pin minio).
- Modify: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (verdict updates).
- Modify: `RELEASE_READINESS.md` (final READY verdict + date).

**Backend & frontend — MVP partials (Phase 1):**
- TZ-3.2-V11-01 PPE warehouse: `backend/app/modules/ppe/warehouse_*.py` (new), `backend/app/migrations/versions/2026MMDD_ppe_warehouse_skeleton.py` (new), `frontend/src/pages/warehouse/*` (new pages), `tests/api/test_ppe_warehouse.py` (new).
- TZ-3.4-V12-01 prescriptions lifecycle: `backend/app/api/routes/prescriptions.py` (modify — finalize lifecycle), `backend/app/modules/inspections/prescriptions_service.py` (modify or new), `tests/api/test_prescriptions_lifecycle.py` (new).
- TZ-6.3-V11-01 coverage gate ≥85%: `.github/workflows/ci.yml` (add scoped coverage job), `scripts/ci/check_backend_coverage_baseline.py` (modify — accept scoped paths), `docs/stabilization/coverage.md` (modify — baseline climb plan).

**Backend & frontend — vNext Phase 5-9 follow-ups (Phase 2):**
- 2.1 Cache-Control uniformity audit: `backend/app/api/routes/*.py` (sweep), `tests/api/test_cache_control_uniformity.py` (new).
- 2.2 Remaining list-endpoint ETag: `backend/app/api/routes/*.py` (named endpoints — see Phase 2 task), `tests/api/test_etag_contracts_*.py` (new).
- 2.3 Slow-query identification: `tests/perf/test_slow_query_inventory.py` (new), `docs/stabilization/perf-baseline.md` (update).
- 2.4 Site Card UI: `frontend/src/pages/sites/SiteCardPage.tsx` (new) — backend already done.
- 2.5 Operational Dashboard frontend: `frontend/src/pages/admin/OperationalDashboardPage.tsx` (new — backend done).
- 2.6 Notifications escalation: `backend/app/modules/notifications/escalation.py` (new), `tests/api/test_notifications_escalation.py` (new), `frontend/src/features/notifications/EscalationConfigPage.tsx` (new).

---

## Phase 0 — CI Stabilization & RB Closure (BLOCKING for MVP READY)

**Why first:** Without `alembic-postgres-upgrade` green on `main`, backend cannot boot in CI, so `restore-drill.yml`, `perf-baseline.yml`, `e2e-smoke.yml` cannot produce evidence. RB-001/002/005 stay open. Release stays NOT READY.

**Strategy (locked with user):** Proactive AST sweep rather than reactive iter-by-iter. One PR for the sweep tool, one or two PRs for batched fixes, then RB workflow re-triggers.

### Task 0.1: Read iter-13 CI verdict and decide branch point

**Files:**
- Read: GitHub Actions run `26294051531` (currently `in_progress`, branch `main` post-iter-13).
- Reference: [`AI_IMPLEMENTATION_REPORT.md`](../../../AI_IMPLEMENTATION_REPORT.md) Session 64 follow-up.

- [ ] **Step 1: Wait for CI to complete, then check verdict**

```bash
gh run watch 26294051531 --exit-status
gh run view 26294051531 --json conclusion,status,jobs --jq '{conclusion, status, failed: [.jobs[] | select(.conclusion=="failure") | .name]}'
```

Expected: one of:
- `conclusion: success` → iter-13 closed alembic. Skip 0.2/0.3, go to 0.4.
- `conclusion: failure` with `alembic-postgres-upgrade` in failed jobs → iter-14 needed. Proceed with 0.2/0.3.
- `conclusion: failure` without `alembic-postgres-upgrade` → alembic green; other failure class. Note it, proceed to 0.4 (RB workflows may need that other failure resolved separately, but it's not the migration chain anymore).

- [ ] **Step 2: Record verdict in working notes**

Create a working scratch line in your terminal session (do NOT commit; this is for the executor's memory):

```
ITER13_VERDICT=<success|alembic-failure|other-failure>
NEXT_FAILURE_MIGRATION=<grep alembic upgrade output for the file that failed>
```

This single state value drives whether 0.2/0.3 run.

### Task 0.2: Build comprehensive AST migration safety pin-test (only if 0.1 verdict == alembic-failure)

**Files:**
- Create: `tests/test_migrations_comprehensive_safety.py`

This test consolidates the four antipatterns historically responsible for `alembic-postgres-upgrade` failures into one analyzer. It supersedes (but does not delete) `tests/test_migrations_enum_create_type_safety.py` and `tests/test_migrations_cross_branch_deps.py` — they stay as narrow guards while this one is the proactive sweep.

The four antipatterns covered:

1. **A1 (iter-8/9):** `postgresql.ENUM(..., name=X)` declared without `create_type=False` after an earlier `.create()` on the same name → `DuplicateObjectError`.
2. **A2 (iter-11):** `op.create_index(..., postgresql_using="gin")` or raw `op.execute("CREATE INDEX ... USING GIN (col)")` where `col` is `sa.JSON()` (not `JSONB`/`TSVECTOR`/`ARRAY`) → `no default operator class`.
3. **A3 (iter-12/13):** enum extension via `<enum>.drop(); <enum>.create()` pattern when the type is already referenced by a column → `DependentObjectsStillExistError`. Prefer `ALTER TYPE ... ADD VALUE IF NOT EXISTS` in a **separate revision** (transaction-per-migration model).
4. **A4 (iter-10):** cross-branch table/column reference without `depends_on = "..."` declaration when the creator migration is on a different branch.

- [ ] **Step 1: Write the failing test scaffold**

Create `tests/test_migrations_comprehensive_safety.py`:

```python
"""Comprehensive AST pin-test for all four classes of Postgres migration
antipatterns that have been observed in this repo since 2026-05-21
billing restore.

Self-contained — runs via `python tests/test_migrations_comprehensive_safety.py`
(no pytest required) AND via `pytest tests/test_migrations_comprehensive_safety.py`.

History:
* A1 (enum double-create) — first seen iter-7 (PR #553), pinned iter-9 (PR #557).
* A4 (cross-branch deps) — pinned iter-10 (PR #559).
* A2 (GIN-on-non-JSONB) — first seen iter-11 (PR #561), pinned here.
* A3 (drop-recreate enum on dependent column) — first seen iter-12/13
  (PRs #563/#564), pinned here.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"

# Columns whose SQL type natively supports GIN. Anything else USING GIN must
# be rejected as A2.
GIN_COMPATIBLE_TYPES = frozenset({"JSONB", "TSVECTOR", "ARRAY"})

# Public API
def find_violations() -> dict[str, list[str]]:
    """Return a dict {antipattern_id: [violation_message, ...]}.

    Empty lists mean clean. Call sites:
    - pytest path: collected as fixture into test functions below.
    - __main__ path: prints summary and exits 0/1.
    """
    files = sorted(MIGRATIONS_DIR.glob("*.py"))
    a1: list[str] = []
    a2: list[str] = []
    a3: list[str] = []
    a4: list[str] = []
    # ... implement four AST visitors here. See sections below for each.
    return {"A1": a1, "A2": a2, "A3": a3, "A4": a4}


if __name__ == "__main__":
    violations = find_violations()
    total = sum(len(v) for v in violations.values())
    if total == 0:
        print("OK — no migration antipattern violations found.")
        sys.exit(0)
    for klass, msgs in violations.items():
        if not msgs:
            continue
        print(f"\n=== {klass} ({len(msgs)} violations) ===")
        for m in msgs:
            print(f"  - {m}")
    sys.exit(1)
```

- [ ] **Step 2: Run scaffold to verify it exits 0 (no violations defined yet)**

```bash
python tests/test_migrations_comprehensive_safety.py
```

Expected: `OK — no migration antipattern violations found.` exit 0.

- [ ] **Step 3: Implement A1 visitor (enum double-create) — copy from existing pin-test**

Open `tests/test_migrations_enum_create_type_safety.py` and lift the A1 visitor into this module. Re-export it from `find_violations()`.

Acceptance: when run against current `main` (post-iter-13), A1 must report 0 violations (iter-9 already closed all known).

- [ ] **Step 4: Run to confirm A1 stays clean**

```bash
python tests/test_migrations_comprehensive_safety.py
```

Expected: exit 0, no A1 messages.

- [ ] **Step 5: Implement A2 visitor (GIN-on-non-JSONB)**

Logic: walk each migration's AST. For every `op.create_index(..., postgresql_using="gin")` and every `op.execute("CREATE INDEX ... USING GIN (col)")`, find the most recent declaration of `col` in this migration or any predecessor migration (use `down_revision` chain — see `test_migrations_cross_branch_deps.py` for traversal). If the column's SQL type is `sa.JSON()` (not JSONB/TSVECTOR/ARRAY), append A2 violation.

```python
# Pseudocode skeleton — replace with full implementation
class GinIndexVisitor(ast.NodeVisitor):
    def __init__(self, file: str, columns_by_type: dict[str, str]):
        self.file = file
        self.columns_by_type = columns_by_type  # filled by predecessor scan
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        # op.create_index(..., postgresql_using="gin", columns=["col"])
        if _is_call(node, "op", "create_index"):
            using = _get_kw(node, "postgresql_using")
            if using == "gin":
                cols = _get_kw(node, "columns") or _positional_at(node, 2)
                for col in cols or []:
                    if self.columns_by_type.get(col, "") not in GIN_COMPATIBLE_TYPES:
                        self.violations.append(
                            f"{self.file}: op.create_index USING GIN over column "
                            f"'{col}' of type '{self.columns_by_type.get(col, '?')}' "
                            "(must be JSONB/TSVECTOR/ARRAY)"
                        )
        # op.execute("CREATE INDEX ... USING GIN (col)") — regex on string literal
        elif _is_call(node, "op", "execute") and len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
            sql = node.args[0].value or ""
            if "USING GIN" in sql.upper():
                # parse column out of "USING GIN (col)" — conservative regex
                import re
                m = re.search(r"USING\s+GIN\s*\(\s*(\w+)\s*\)", sql, re.IGNORECASE)
                if m:
                    col = m.group(1)
                    if self.columns_by_type.get(col, "") not in GIN_COMPATIBLE_TYPES:
                        self.violations.append(
                            f"{self.file}: op.execute USING GIN over column "
                            f"'{col}' of type '{self.columns_by_type.get(col, '?')}'"
                        )
        self.generic_visit(node)
```

Wire it into `find_violations()`.

- [ ] **Step 6: Run to detect A2 violations on current main**

```bash
python tests/test_migrations_comprehensive_safety.py
```

Expected: exit 1 OR exit 0. iter-11 closed `next47`. If grep at planning time (per earlier exploration) found only that one, expect 0. If sweep finds additional ones, they're new finds — record them; they're real bugs even if CI hasn't tripped them yet.

If finds appear: each `<file>:<msg>` is a follow-up fix in Task 0.3.

- [ ] **Step 7: Implement A3 visitor (drop-recreate enum on dependent column)**

Logic: scan for AST pattern `<name>.drop(...)` immediately followed (next statement OR within ≤3 statements) by `<name>.create(...)` for the **same** identifier. Cross-check: was `<name>` previously declared as `postgresql.ENUM(..., name="X")` AND is any column of type `X` defined in a predecessor migration? If both yes → A3 violation; recommend ALTER TYPE ADD VALUE in a separate revision (cite the next55/next55b split as precedent).

```python
class DropRecreatePatternVisitor(ast.NodeVisitor):
    def __init__(self, file: str, enum_names_to_existing_cols: dict[str, list[str]]):
        self.file = file
        self.enum_cols = enum_names_to_existing_cols
        self.violations: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name != "upgrade":
            self.generic_visit(node)
            return
        stmts = node.body
        for i, stmt in enumerate(stmts):
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
                continue
            call = stmt.value
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "drop"):
                continue
            # Identify drop target identifier
            target = call.func.value.id if isinstance(call.func.value, ast.Name) else None
            if target is None:
                continue
            # Look ahead ≤3 stmts for matching <target>.create(...)
            for follow in stmts[i+1:i+4]:
                if (isinstance(follow, ast.Expr)
                        and isinstance(follow.value, ast.Call)
                        and isinstance(follow.value.func, ast.Attribute)
                        and follow.value.func.attr == "create"
                        and isinstance(follow.value.func.value, ast.Name)
                        and follow.value.func.value.id == target):
                    # Check: is target a postgresql.ENUM bound to a name that
                    # already has a column of that type?
                    enum_name = self._resolve_enum_name(node, target)
                    if enum_name and self.enum_cols.get(enum_name):
                        self.violations.append(
                            f"{self.file}: drop-recreate of enum '{enum_name}' "
                            f"while column(s) {self.enum_cols[enum_name]} still "
                            "reference it — use ALTER TYPE ADD VALUE in a "
                            "separate revision (precedent: next55 → next55b split)"
                        )
                    break
        self.generic_visit(node)

    def _resolve_enum_name(self, fn: ast.FunctionDef, var_name: str) -> str | None:
        """Find `<var_name> = postgresql.ENUM(..., name='X')` assignment in fn body."""
        for stmt in fn.body:
            if (isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == var_name
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Attribute)
                    and stmt.value.func.attr == "ENUM"):
                for kw in stmt.value.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
        return None
```

Wire into `find_violations()`. Note: the `enum_names_to_existing_cols` dict must be built by a pre-pass over the migration DAG predecessors. Reuse the parser in `test_migrations_cross_branch_deps.py`.

- [ ] **Step 8: Run to detect A3 violations on current main**

```bash
python tests/test_migrations_comprehensive_safety.py
```

Expected: A3 reports 0 (next55 was the only known and iter-13 fixed it). If finds appear, they're follow-up fixes.

- [ ] **Step 9: Implement A4 visitor (cross-branch deps) — lift from existing pin-test**

Copy the implementation from `tests/test_migrations_cross_branch_deps.py` into the new module. Wire into `find_violations()`. iter-10 fixed all known A4 — expect 0.

- [ ] **Step 10: Run all four classes together**

```bash
python tests/test_migrations_comprehensive_safety.py
```

Expected outcomes (per class):
- A1: 0 (iter-8/9 closed)
- A2: 0 or N (any N is iter-14 scope)
- A3: 0 (iter-13 closed)
- A4: 0 (iter-10 closed)

Total violations N: drives Task 0.3 scope.

- [ ] **Step 11: Add pytest entry points so the analyzer runs in `backend-tests` CI job**

Append to `tests/test_migrations_comprehensive_safety.py`:

```python
import pytest

@pytest.fixture(scope="module")
def violations() -> dict[str, list[str]]:
    return find_violations()

def test_a1_no_enum_double_create(violations: dict[str, list[str]]) -> None:
    assert violations["A1"] == [], "\n".join(violations["A1"])

def test_a2_no_gin_on_non_jsonb(violations: dict[str, list[str]]) -> None:
    assert violations["A2"] == [], "\n".join(violations["A2"])

def test_a3_no_enum_drop_recreate_on_dependent_column(violations: dict[str, list[str]]) -> None:
    assert violations["A3"] == [], "\n".join(violations["A3"])

def test_a4_no_missing_cross_branch_depends_on(violations: dict[str, list[str]]) -> None:
    assert violations["A4"] == [], "\n".join(violations["A4"])
```

- [ ] **Step 12: Commit the sweep tool (regardless of whether violations found)**

```bash
git checkout -b fix/iter-14-comprehensive-migration-sweep
git add tests/test_migrations_comprehensive_safety.py
git commit -m "$(cat <<'EOF'
test(migrations): add comprehensive AST pin-test for 4 Postgres antipatterns

Consolidates 4 classes of alembic-postgres-upgrade failure observed in
iter-7..13:
- A1: enum double-create (DuplicateObjectError)
- A2: GIN index on non-JSONB column (no default opclass)
- A3: drop-recreate enum with dependent column (DependentObjectsStillExist)
- A4: cross-branch table/column reference without depends_on

Proactive sweep replaces reactive iter-by-iter pattern. Runs in
backend-tests CI job; failures are blocking.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 0.3: Fix all sweep violations in a single batched PR (only if 0.2 found violations)

**Files:** determined by 0.2 output — typically 5-15 files under `backend/app/migrations/versions/`.

For each violation, apply the fix that the antipattern's recommendation prescribes:

- **A1 fix:** change `postgresql.ENUM(..., name=X)` to `postgresql.ENUM(..., name=X, create_type=False)`. Reference precedent: PR #555 (7 migrations).
- **A2 fix:** change column type from `sa.JSON()` to `postgresql.JSONB(astext_type=sa.Text())`, change `server_default` to explicit `sa.text("'{}'::jsonb")` cast. Reference precedent: PR #561 (`20260318_next47:21`).
- **A3 fix:** split the migration into two revisions:
  - Original migration: add new enum values via `ALTER TYPE ... ADD VALUE IF NOT EXISTS '<v>'` under a `bind.dialect.name == "postgresql"` gate; remove any data-update statement that references the new values.
  - New `<orig>b_<topic>_data.py` revision: do the data updates. Down = no-op.
  - Update `down_revision` of the **next** migration in the chain to point at the new `b` revision.
  Reference precedent: PR #564 (next55 → next55 + next55b split).
- **A4 fix:** add `depends_on = "<latest-creator-rev-on-other-branch>"` at the top of the migration that references the cross-branch table/column. Reference precedent: PR #559 (`next66`, `next67`).

- [ ] **Step 1: For each violation, write the smallest-diff fix per the rules above**

No code block here because the exact code depends on what the sweep reports. Use the precedents in the same files (cited above) as templates. One commit per antipattern class (so a single PR has up to 4 commits: A1-batch, A2-batch, A3-batch, A4-batch). Skip a commit if its class reported 0.

- [ ] **Step 2: Re-run sweep to verify all clean**

```bash
python tests/test_migrations_comprehensive_safety.py
```

Expected: exit 0 (no violations remain).

- [ ] **Step 3: Run iter-9 + iter-10 + iter-13 pin-tests to confirm no regression**

```bash
python tests/test_migrations_enum_create_type_safety.py
python tests/test_migrations_cross_branch_deps.py
```

Expected: both exit 0.

- [ ] **Step 4: Push branch, open PR, watch alembic-postgres-upgrade job**

```bash
git push -u origin fix/iter-14-comprehensive-migration-sweep
gh pr create --fill --title "fix(migrations): iter-14 — proactive AST sweep closes 4 antipattern classes" --body "$(cat <<'EOF'
## Summary
- Adds comprehensive AST pin-test `tests/test_migrations_comprehensive_safety.py` covering all 4 classes of Postgres alembic-postgres-upgrade failure observed in iter-7..13.
- Fixes <N> migrations across <A1/A2/A3/A4> classes surfaced by the sweep.
- Replaces reactive iter-by-iter chase with one proactive PR.

## Test plan
- [ ] CI `backend-tests` job runs comprehensive sweep pin-test, exits 0.
- [ ] CI `alembic-postgres-upgrade` job runs to completion (no migration class blocks boot).
- [ ] iter-9/10/13 pin-tests still green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
```

Expected: `alembic-postgres-upgrade` green. If still red on an unrelated/new failure class, document as iter-15 scope (rare per the sweep coverage), do not loop here.

- [ ] **Step 5: Merge after CI green**

```bash
gh pr merge --merge --auto
```

### Task 0.4: Re-trigger RB-001 (restore-drill.yml) and close known LibreOffice/minio defects

**Files:**
- Modify: `.github/workflows/restore-drill.yml`
- Modify: `scripts/restore_drill.py` (only if pinning minio image is rejected and verifier must be loosened — but prefer pinning over relaxing).

Background: per [memory `app_level_defects_post_billing`](../../../C:/Users/karka/.claude/projects/D---------------------------------/memory/app_level_defects_post_billing.md) (still valid per `KNOWN_LIMITATIONS.md`), restore-drill postgres-minio mode is blocked by:
- **#2:** `bitnamilegacy/minio:latest` drifts on default S3 metadata vs the version the verifier was written against. 3/3 objects mismatch.
- **#3:** restore-drill workflow doesn't install LibreOffice, but `backend.app.cli.main health check` requires `soffice`. Exit 4.

- [ ] **Step 1: Add LibreOffice install step to restore-drill.yml**

Open `.github/workflows/restore-drill.yml`. Find the job step block before `run: python scripts/restore_drill.py ...`. Add:

```yaml
      - name: Install LibreOffice (required by smoke_boot health check)
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends libreoffice-core
          which soffice && soffice --version
```

- [ ] **Step 2: Pin bitnamilegacy/minio to a known-compatible tag**

In the same workflow, find the minio service container declaration. Change `image: bitnamilegacy/minio:latest` to `image: bitnamilegacy/minio:2024.12.18` (or the closest tag to what `docker-compose.yml` uses for local dev — verify with: `grep -i minio docker-compose.yml`).

If no tagged release of `bitnamilegacy/minio` matches, fall back to `minio/minio:RELEASE.2024-12-18T13-15-44Z` (the upstream image used by local dev), but you'll need to add `command: server /data` because the upstream image doesn't bake that in.

- [ ] **Step 3: Trigger restore-drill against main**

```bash
gh workflow run restore-drill.yml --ref=main
gh run watch $(gh run list --workflow=restore-drill.yml --limit=1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: green. Artifact `restore-drill-evidence` uploaded with `latest-postgres-minio.json` showing `accept: true`.

- [ ] **Step 4: If green, verify artifact**

```bash
gh run download $(gh run list --workflow=restore-drill.yml --limit=1 --json databaseId --jq '.[0].databaseId') -n restore-drill-evidence -D /tmp/rd
cat /tmp/rd/latest-postgres-minio.json | jq '{accept, mismatches: .object_mismatches}'
```

Expected: `accept: true`, `mismatches: []`.

- [ ] **Step 5: Commit workflow change**

```bash
git add .github/workflows/restore-drill.yml
git commit -m "$(cat <<'EOF'
ci(restore-drill): install LibreOffice + pin minio image

Closes 2 known post-billing defects blocking RB-001 postgres-minio mode:
- smoke_boot health check requires soffice; was missing in workflow runner.
- bitnamilegacy/minio:latest drifted from what verifier was written against;
  pin to a known-compatible tag to make object metadata stable.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 0.5: Re-trigger RB-002 (perf-baseline.yml) and validate

**Files:**
- Trigger: `.github/workflows/perf-baseline.yml`
- Read: `artifacts/perf/nightly/trend-manifest.json` (output)

- [ ] **Step 1: Trigger and watch**

```bash
gh workflow run perf-baseline.yml --ref=main
gh run watch $(gh run list --workflow=perf-baseline.yml --limit=1 --json databaseId --jq '.[0].databaseId') --exit-status
```

- [ ] **Step 2: If green, fetch and inspect manifest**

```bash
gh run download $(gh run list --workflow=perf-baseline.yml --limit=1 --json databaseId --jq '.[0].databaseId') -n perf-baseline-artifacts -D /tmp/perf
ls /tmp/perf/artifacts/perf/nightly/
cat /tmp/perf/artifacts/perf/nightly/trend-manifest.json | jq '{generated_at, baseline_pass: .baseline.accept, percentiles}'
```

Expected: `trend-manifest.json` present, `summary.md` present, `baseline.accept: true`.

- [ ] **Step 3: If perf-baseline still red, identify class**

Check the failure log. Common possible failures:
- Backend boot fail (alembic still red) → loop back to Task 0.1.
- Perf threshold regression → scope is real perf work; document in handoff and exit Phase 0 with RB-002 still partial.
- LO/PDF perf path missing — same LibreOffice issue as 0.4. If yes, add the install step to `perf-baseline.yml` too.

No commit unless workflow file changed.

### Task 0.6: Re-trigger RB-005 (e2e-smoke.yml) and fix `/no-access` page regression

**Files:**
- Trigger: `.github/workflows/e2e-smoke.yml`
- Read: `frontend/src/router/AppRouter.tsx` (route definition for `/no-access`)
- Read: `frontend/src/pages/no-access/*` (heading element)
- Modify: whichever frontend file regressed during the 9-week billing window.

Background: per [memory](../../../C:/Users/karka/.claude/projects/D---------------------------------/memory/app_level_defects_post_billing.md), Playwright `expect(page.getByRole("heading", { name: "Доступ ограничен" })).toBeVisible()` failed on `/no-access`. Likely causes: heading text changed, heading element type changed, route restructured.

- [ ] **Step 1: Run e2e-smoke locally first to reproduce**

```bash
cd frontend
npm ci
npm run build
npm run e2e -- --grep "no-access"
```

Expected: at least one failing assertion. Capture the actual page content vs. what the test asserts.

If the test passes locally but fails in CI, the regression may be CI-specific (env, headless rendering). Note and proceed to Step 2.

- [ ] **Step 2: Inspect the page source**

```bash
grep -rn "Доступ ограничен" frontend/src/
grep -rn "no-access" frontend/src/router/
```

Identify the actual current heading text and element type on `/no-access`.

- [ ] **Step 3: Decide: fix the page or fix the test**

- If the heading text was deliberately changed during the billing window → update the Playwright test selector.
- If the page regressed (heading missing, element type changed unintentionally) → fix the page to restore the contract.

Pick the smallest correct fix per TZ §E (don't break working functionality).

- [ ] **Step 4: Apply fix, commit**

```bash
# (whatever single-file edit was decided in Step 3)
git add <changed-file>
git commit -m "fix(frontend|tests): restore /no-access page contract for e2e-smoke"
```

- [ ] **Step 5: Push, re-trigger e2e-smoke, verify green**

```bash
git push
gh workflow run e2e-smoke.yml --ref=main
gh run watch $(gh run list --workflow=e2e-smoke.yml --limit=1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: green. Artifact `e2e-smoke-access-enforcement` uploaded.

### Task 0.7: Update RELEASE_BLOCKERS_STATUS.md and RELEASE_READINESS.md → READY

**Files:**
- Modify: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Modify: `RELEASE_READINESS.md`
- Modify: `KNOWN_LIMITATIONS.md` (clear the "CI stabilization limitations" block)
- Modify: `GAP_REPORT.md` (clear the `Iter-restoration` row)

The procedure is documented in `RELEASE_READINESS.md` "How to update the release verdict" — follow it exactly.

- [ ] **Step 1: Edit `RELEASE_BLOCKERS_STATUS.md` first (canonical source)**

For each of RB-001/002/005:
- Change `- [ ]` to `- [x]`.
- Append a `**Status: DONE** (2026-MM-DD)` line under the bullet with the artifact URL from Task 0.4/0.5/0.6.

Change `**Current status:** 3/6 blockers closed (RB-003 partial, RB-004 done, RB-006 done).` → `**Current status:** 6/6 blockers closed.`

Update `## Recent stabilization activity` block: append the iter-14 PR row and a single-line closure note "All 6 release blockers closed as of 2026-MM-DD; binary go/no-go passed."

Bump `Updated on (UTC)` to today.

- [ ] **Step 2: Sync `RELEASE_READINESS.md`**

Edit the "Release-critical verdict inputs" table — change all `partial`/`missing` for RC-001/002/006 to `done`.

Edit "Launch readiness verdict":
```markdown
- **Verdict date (UTC):** 2026-MM-DD
- **Verdict:** **READY** (6 of 6 blockers closed)
- **Path to closure:** N/A — all blockers green; release window may proceed.
```

Bump `Updated on (UTC)`.

- [ ] **Step 3: Clear stale `KNOWN_LIMITATIONS.md` "CI stabilization" block**

Replace the "CI stabilization limitations (added 2026-05-21, post-billing-restore)" section with a one-paragraph closure note linking to the iter-14 PR.

- [ ] **Step 4: Clear `GAP_REPORT.md` "Iter-restoration" row**

Remove the `Iter-restoration | Post-billing CI rot | partial` row from the "Post-billing-restore stabilization" table (the table can stay if there are other entries; otherwise remove the section).

- [ ] **Step 5: Update AI_IMPLEMENTATION_REPORT.md handoff**

Add a new "Last Agent Handoff" entry at the top documenting: Phase 0 closure, iter-14 PR, RB-001/002/005 green, MVP READY verdict date. Set "Next Steps" to point at Phase 1 of this plan.

- [ ] **Step 6: Commit doc bundle, open PR, merge**

```bash
git checkout -b docs/mvp-ready-verdict-closure
git add docs/stabilization/RELEASE_BLOCKERS_STATUS.md RELEASE_READINESS.md KNOWN_LIMITATIONS.md GAP_REPORT.md AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(release): mark MVP READY — RB-001/002/005 closed, 6/6 blockers green"
git push -u origin docs/mvp-ready-verdict-closure
gh pr create --fill --title "docs(release): MVP READY verdict — 6/6 blockers closed"
gh pr merge --merge --auto
```

**Phase 0 Definition of Done:** `RELEASE_READINESS.md` shows `Verdict: READY` AND `RELEASE_BLOCKERS_STATUS.md` shows 6/6 `[x]` AND `AI_IMPLEMENTATION_REPORT.md` documents the closure.

---

## Phase 1 — MVP Partials Closure

Three matrix items remain `partial`/`missing` (priority p2, tagged `[v1.1]`/`[v1.2]`). With MVP READY in hand from Phase 0, these can land at a lower urgency but should be closed to clear the matrix.

Each task here has medium granularity. Before starting a task, the executor should spawn a per-task sub-plan with full TDD steps (use this plan's Phase 0 task structure as the template). The fields below scope each sub-plan.

### Task 1.1: PPE warehouse skeleton (TZ-3.2-V11-01)

**Status today:** `missing`, p2, `[v1.1]`.
**TZ reference:** §A.3.2 "склад (остатки/партии/сертификаты/инвентаризация) — skeleton `[v1.1]`"; full vNext spec §B.11 (`vNext §12.3`).

**Scope for this skeleton (NOT full B.11):**
- Domain entities: `WarehouseItem` (nomenclature line), `WarehouseStock` (per-site stock level), `WarehouseBatch` (FIFO batch with cert + expiry), `WarehouseMovement` (in/out/transfer/writeoff audit row).
- API endpoints (REST, tenant-scoped, RBAC-guarded):
  - `GET /api/v1/ppe/warehouse/items` (list with filters: site, hazard class)
  - `POST /api/v1/ppe/warehouse/items` (create nomenclature line)
  - `GET /api/v1/ppe/warehouse/stock?site_id=...`
  - `POST /api/v1/ppe/warehouse/movements` (in/out/transfer/writeoff)
  - `GET /api/v1/ppe/warehouse/batches?item_id=...`
- Frontend pages (read-only minimal viable):
  - `/warehouse/items` — items list with filter chips
  - `/warehouse/stock/:siteId` — stock levels per site, batch breakdown
  - `/warehouse/movements` — movement journal (paginated, filterable)
- Tests: API contract (CRUD happy path + tenant-isolation + RBAC deny for non-warehouse role), one e2e smoke (list + filter + paginate).
- Migration: `2026MMDD_ppe_warehouse_skeleton.py` — additive, follows iter-14 antipattern rules.
- Matrix update: `TZ-3.2-V11-01` → `partial` (skeleton present, full B.11 still future) with evidence paths.

**Out of scope (defer to full vNext §12):** mobile/QR issue, supplier integration, demand forecasting, budget link, reservation engine.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-ppe-warehouse-skeleton.md`.

**Acceptance:** new endpoints return 200/4xx as contracted, frontend pages render without crash, matrix row updated, CHANGELOG.md has entry.

### Task 1.2: Prescriptions lifecycle finalization (TZ-3.4-V12-01)

**Status today:** `partial`, p2, `[v1.2]`.
**TZ reference:** §A.3.4 "предписания (prescriptions): skeleton `[v1.2]`"; full vNext §B.13 (`vNext §14.3`).

**Scope:**
- Current state: `backend/app/api/routes/prescriptions.py` exists; access parity test (`backend/tests/test_prescriptions_access_parity.py`) green. Lifecycle/status workflow NOT finalized.
- Add: lifecycle states `draft → issued → in_progress → evidence_attached → verified → closed | rejected | overdue`, with allowed transitions enforced server-side (state-machine + 409 on illegal transitions).
- Add: deadline tracking — `due_at`, computed `overdue_at` boolean, scheduled job that flips `in_progress` → `overdue` when `due_at < now`.
- Add: evidence attachment endpoint (file upload via existing files module, link back via `prescription_evidence` join table).
- Add: domain event `PrescriptionStatusChanged` → outbox.
- Tests: state-transition matrix (allowed + denied), deadline overdue auto-flip, evidence upload + retrieve, RBAC matrix.
- Matrix update: `TZ-3.4-V12-01` → `done` (skeleton OR full per scope) with evidence paths.

**Out of scope (defer to vNext §14.3 full):** BBS audit linkage, escalation tree, repeat-inspection auto-schedule, % closure analytics dashboard.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-prescriptions-lifecycle.md`.

**Acceptance:** state-machine tests green, scheduled job test green, matrix row updated, CHANGELOG.md has entry.

### Task 1.3: Coverage gate ≥85% for core/domain/services (TZ-6.3-V11-01)

**Status today:** `missing`, p2, `[v1.1]`.
**TZ reference:** §A.6.3 "coverage gate `core/domain/services` ≥ 85% — `[v1.1]` (текущий — план подъёма зафиксирован)".

**Scope:**
- Add scoped coverage targets in CI:
  - `python -m pytest --cov=backend/app/core --cov=backend/app/domain --cov=backend/app/services --cov-report=json:artifacts/coverage_scoped.json tests/`
  - Run `scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage_scoped.json --baseline docs/stabilization/backend_coverage_scoped_baseline.json --min-percentage 85`
- Capture current baseline % per package (likely <85 today; if <85, set baseline to today's number and add a *climb plan* — i.e. baseline ratchets up by 1% per merged PR until it hits 85).
- Document climb plan in `docs/stabilization/coverage.md`.
- Matrix update: `TZ-6.3-V11-01` → `done` (gate operational, climb in progress) OR `partial` (gate present, target not yet at 85%) — pick the honest one and document.

**Out of scope:** raising coverage to 85% if today's number is far below (that's separate per-module work). The gate's existence is the deliverable.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-coverage-gate-scoped.md`.

**Acceptance:** CI job `backend-tests-scoped-coverage` exists and enforces baseline; baseline + climb plan documented; matrix row updated.

**Phase 1 Definition of Done:** `docs/audit/TZ_COVERAGE_MATRIX.md` has no remaining `[v1.1]` or `[v1.2]` rows with `missing` status in the priority p2 bucket (1.1, 1.2, 1.3 updated to `partial`/`done` with evidence).

---

## Phase 2 — vNext Phase 5-9 Polish Follow-ups

Phases 5-9 were marked `COMPLETE` in TZ §C as of Session 64, with explicit "Optional polish (не блокер)" follow-ups remaining. The user asked to include these for "максимально доработать" closure.

Each task spawns its own sub-plan. Granularity here is roadmap-level; sub-plans deepen to TDD steps.

### Task 2.1: Cache-Control uniformity audit (Phase 9.2 follow-up, called out in S58/S59 handoff)

**Why:** Per [memory `workflow_prodolzhay_po_tz`](../../../C:/Users/karka/.claude/projects/D---------------------------------/memory/workflow_prodolzhay_po_tz.md), S58 → S59 closed this for some endpoints but a full sweep was deferred. ETag without consistent Cache-Control = client behavior varies per browser cache heuristic.

**Scope:**
- Audit every list endpoint that has ETag (16 per S53 handoff).
- Define canonical `Cache-Control` policy: `private, must-revalidate, max-age=0` for authenticated tenant-scoped list endpoints (covers our use case — clients still get 304 fast paths via ETag without holding stale data in cache).
- Add helper `apply_list_cache_headers(response)` in `backend/app/services/http_cache.py` (extend existing helper or create).
- Sweep callsites; add contract test that asserts every list endpoint returns the canonical header.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-cache-control-uniformity.md`.

### Task 2.2: ETag for remaining list endpoints (Phase 9.2 tail-end)

**Why:** S53 handoff: "16 list endpoints carry ETag, 116 contract tests total; remaining list endpoints + service-level Redis cache + Cache-Control uniformity audit + slow-query identification + date partitioning remain follow-ups."

**Scope:**
- Inventory all `@router.get(...)` endpoints that return list responses (regex/AST sweep).
- Subtract the 16 already covered.
- For the remainder, apply the `compute_list_etag` helper (S50) — one PR per ~5 endpoints to keep diffs reviewable.
- Add contract tests in the established style.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-etag-remaining-list-endpoints.md`.

### Task 2.3: Slow-query identification (Phase 9.1 follow-up)

**Why:** S46 pinned 24 query benchmarks but didn't run them as a top-N slowest report. Without the report, optimization is unfocused.

**Scope:**
- Add `tests/perf/test_slow_query_inventory.py` — runs the 24 (or more, if expanded) benchmark queries, captures p95 latency, emits a sorted Top-N report as a CI artifact.
- Threshold: any query p95 > 1s flags as "slow" per TZ §B.30 perf SLO.
- Output artifact: `artifacts/perf/slow-query-report.json` consumed by perf-baseline job.
- Document method in `docs/stabilization/perf-baseline.md`.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-slow-query-identification.md`.

### Task 2.4: Site Card UI (Phase 3.3 follow-up — Employee Card is done; Site Card backend exists but UI deferred)

**Why:** TZ §C: "Site Card pending". Symmetric counterpart to Employee Card (which was closed S19-21 with `GET /api/v1/employees/{id}` + `EmployeeCardPage.tsx` 11 tabs).

**Scope:**
- Verify `GET /api/v1/sites/{id}` aggregate endpoint exists (likely does — confirm in `backend/app/api/routes/sites.py`).
- Build `frontend/src/pages/sites/SiteCardPage.tsx` — same tab-based layout as Employee Card but with site-relevant tabs: Overview, People assigned, Departments, Workplaces (positions), Equipment, Documents (passport/instructions), Risks, Incidents, Inspections, Briefings, Audit log.
- E2E smoke: site card opens, all tabs render without crash.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-site-card-ui.md`.

### Task 2.5: Operational Dashboard frontend (Phase 2.x — backend done, frontend pending)

**Why:** TZ §C: "vNext Phase 2 (Operational dashboard / Health checks) — backend `done`, frontend `pending`."

**Scope:**
- Build `frontend/src/pages/admin/OperationalDashboardPage.tsx` consuming the existing backend dashboard module (`backend/app/modules/operational_dashboard/*`).
- Layout: tiles for outbox depth, dead-letter count, job queue size, retry success rate, last incident-class error, slow-query top 3.
- Auto-refresh every 30s with manual refresh button.
- Permission gate: visible to roles `admin`, `owner`, `hse_head` only.
- E2E smoke: dashboard opens, tiles render, refresh works.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-operational-dashboard-frontend.md`.

### Task 2.6: Notifications escalation/provider orchestration completeness (RC-011)

**Why:** Per `KNOWN_LIMITATIONS.md` RC-011: "Notifications escalation/provider orchestration is not feature-complete" — still `missing`. Phase 8 closed analytics-side, this is notifications-side.

**Scope:**
- Add escalation policy data model: `NotificationEscalationRule { trigger_event, delay_minutes, target_role, channel_preference }`.
- Provider orchestration: cascade across channels (in-app → email → SMS → Telegram) on no-ack within delay.
- Tenant-configurable rules via `EscalationConfigPage.tsx` admin UI.
- Tests: rule evaluation, cascade order, ack stops escalation, all-channel failure logged.
- Update RC-011 in `KNOWN_LIMITATIONS.md` → `done` with evidence paths.

**Sub-plan filename:** `docs/superpowers/plans/2026-MM-DD-notifications-escalation.md`.

**Phase 2 Definition of Done:** all 6 sub-plans created and executed; `AI_IMPLEMENTATION_REPORT.md` documents closure of each; no `Optional polish (не блокер)` lines remain in Phase 5-9 sections of `TZ_FULL_UNIFIED.md` §C.

---

## Per-task hygiene checklist (applies to every task above)

Per TZ §E, every closing PR must:

- [ ] Obey §E.1 ARCHITECTURE_RULES: no breaking change to working modules; feature flags for new behavior; additive migrations; tenant isolation preserved; bounded contexts not crossed directly; heavy work in workers.
- [ ] Obey §E.2 ENGINEERING_RULES: unit + integration + (where applicable) e2e tests; OpenAPI updated for new endpoints; `CHANGELOG.md` entry; strict typing on backend (mypy) and frontend (tsc); correlation-id in any new log line.
- [ ] Obey §E.3 PRODUCT_UX_RULES: new screen tied to a named user role + scenario; new entity attached to existing master data; massive operations preview/progress/rollback; mobile features account for offline.
- [ ] Answer §E.4 SIX_QUESTIONS in the PR description.
- [ ] Update `docs/audit/TZ_COVERAGE_MATRIX.md` for any matrix-tracked requirement.
- [ ] Update `AI_IMPLEMENTATION_REPORT.md` handoff for the next session (next exact step).

---

## Execution sequence summary

1. **Phase 0** (this plan, fully detailed): execute in order. Stop after Task 0.7 with MVP READY verdict.
2. **Phase 1** (medium detail): write sub-plan per task on entry, execute, close.
3. **Phase 2** (roadmap): write sub-plan per task on entry, execute, close.

Parallelization: within Phase 1, Tasks 1.1, 1.2, 1.3 are independent (different domains) — can be done by separate subagents. Within Phase 2, Tasks 2.1, 2.2, 2.3, 2.4, 2.5, 2.6 are also independent.

Phase 0 is NOT parallelizable internally — Tasks 0.1 → 0.7 are strict-sequential because each depends on the previous.

---

## Self-review notes (applied during authoring per writing-plans skill)

- **Spec coverage:** Phase 0 maps to RC-001/002/006 (RB-001/002/005) which is the binary go/no-go gate. Phase 1 maps to TZ-3.2-V11-01, TZ-3.4-V12-01, TZ-6.3-V11-01 (the only 3 partial/missing matrix rows). Phase 2 maps to named "Optional polish" follow-ups in TZ §C + RC-011. Together: all open items in the matrix, blockers checklist, KNOWN_LIMITATIONS, and Phase 5-9 follow-ups.
- **Placeholder scan:** Phase 0 tasks contain code blocks and exact bash. Phase 1 and 2 intentionally defer per-task TDD detail to sub-plans (declared up front in the file header) — this is per writing-plans skill's "If the spec covers multiple independent subsystems, suggest breaking this into separate plans." rule. Each Phase 1/2 task has concrete file paths, scope inclusions, scope exclusions, and acceptance criteria — enough for an executor to write a sub-plan without re-deriving requirements.
- **Type consistency:** referenced types and function signatures are either lifted from existing files (`compute_list_etag`, `OutboxStatus.DEAD`) or marked as new with their target module noted.
- **Risk acknowledged:** Phase 0 Task 0.4/0.5/0.6 may surface additional unknown failures when RB workflows are re-triggered. Each task includes a "if still red" branch so the plan doesn't dead-end. iter-14 sweep should reduce but cannot eliminate this.
