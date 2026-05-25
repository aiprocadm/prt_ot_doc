# Release Blockers (RB-001, RB-002, RB-005) — Wave 37 Guide

## Executive Summary

Wave 37 researched and documented 3 critical Release Blockers:
- **RB-001 Restore Drill:** Backup/restore validation (partial → needs done)
- **RB-002 Perf Baseline:** Performance manifest generation (partial → needs done)
- **RB-005 E2E Diagnostics:** Access enforcement smoke tests (missing → needs done)

All three require CI environment (GitHub Actions) to execute due to dependencies:
- RB-001: Postgres 16 + MinIO
- RB-002: Docker Compose
- RB-005: Node.js 20 + Playwright

This guide provides exact commands, prerequisites, expected artifacts, and manual dispatch instructions.

---

## RB-001: Restore Drill Closure

### Status
- Current: `partial`
- Target: `done`
- Workflow: `.github/workflows/restore-drill.yml`
- Script: `scripts/restore_drill.py`

### Two Modes Available

#### Mode 1: SQLite (local, no dependencies)
```bash
python scripts/restore_drill.py --mode sqlite --output-dir artifacts/restore-drill
```

Expected artifact: `artifacts/restore-drill/latest-sqlite.json`

#### Mode 2: Postgres-MinIO (CI, provider-like)
```bash
python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill \
  --postgres-source-dsn postgresql://postgres:postgres@localhost:5432/restore_drill_source \
  --postgres-restore-dsn postgresql://postgres:postgres@localhost:5432/restore_drill_restore \
  --minio-endpoint localhost:9000 \
  --minio-access-key minioadmin \
  --minio-secret-key minioadmin
```

Expected artifact: `artifacts/restore-drill/latest-postgres-minio.json`

### Acceptance Criteria (JSON verification)
```json
{
  "success": true,
  "restore": {
    "verification": {
      "counts_match": true,
      "documents_checksum_match": true,
      "object_content_and_metadata_match": true,
      "object_mismatches": []
    }
  },
  "smoke_boot": {
    "exit_code": 0
  }
}
```

All conditions must be `true` for acceptance.

### Run via GitHub Actions (Recommended)
1. Go to **Actions** tab
2. Select **"Restore Drill"** workflow
3. Click **"Run workflow"** → select **Main branch** → **"Run workflow"**
4. Wait for completion (~5–10 min)
5. Download artifact: **restore-drill-evidence**
6. Extract and verify: `latest-postgres-minio.json` contains `"success": true`

### Documentation
- Full guide: `docs/stabilization/restore-drill.md`
- Runbook: `docs/runbooks/RESTORE_TENANT.md`
- Mapped to: RC-001 (Restore drill acceptance), RC-012 (RTO/RPO closure)

---

## RB-002: Perf Baseline Closure

### Status
- Current: `partial`
- Target: `done`
- Workflow: `.github/workflows/perf-baseline.yml`
- Script: `scripts/perf/api_load.py` + `scripts/perf/scenarios.json`

### Scenarios Covered
1. `/health` — auth/session readiness
2. `/api/v1/dashboard/summary` — dashboard aggregate read
3. `/api/v1/templates` — list/read endpoint
4. `/api/v1/search/suggest?q=doc` — search latency
5. `POST /api/v1/documents/generate` + apply-headers — document generation flow
6. Files upload/finalize/download-url — file flow
7. Job status transitions — async job lifecycle
8. (Additional custom scenarios in nightly profile)

### Performance Targets

| Endpoint | p50 target | p95 max | p99 max | Throughput min | Error-rate max |
|----------|-----------|---------|---------|----------------|----------------|
| `/health` | ≤ 150 ms | ≤ 250 ms | ≤ 600 ms | ≥ 30 rps | ≤ 2.0% |
| `/api/v1/dashboard/summary` | ≤ 300 ms | ≤ 600 ms | ≤ 1200 ms | ≥ 15 rps | ≤ 2.0% |
| `/api/v1/templates` | ≤ 250 ms | ≤ 500 ms | ≤ 1000 ms | ≥ 18 rps | ≤ 2.0% |

### Expected Artifacts

1. `artifacts/perf/nightly/trend-manifest.json` — consolidated results
```json
{
  "generated_at_utc": "2026-04-30T...",
  "profile": "nightly_baseline",
  "results": [
    {
      "path": "/health",
      "p50_ms": 120,
      "p95_ms": 180,
      "p99_ms": 400,
      "throughput_rps": 35,
      "error_rate": 0.0
    }
    // ... more endpoints
  ]
}
```

2. `artifacts/perf/nightly/summary.md` — markdown table
3. `artifacts/perf/nightly/summary.csv` — CSV format for trend analysis

### Run via GitHub Actions (Recommended)
1. Go to **Actions** tab
2. Select **"Perf Baseline"** workflow
3. Click **"Run workflow"** → select **Main branch** → **"Run workflow"**
4. Wait for completion (~10–15 min, includes Docker build)
5. Download artifact: **perf-baseline-{run_id}**
6. Extract and verify:
   - `trend-manifest.json` has `"profile": "nightly_baseline"`
   - All results have `p95_ms` and `throughput_rps` values
   - No errors or missing results

### Documentation
- Full guide: `docs/stabilization/perf-baseline.md`
- Mapped to: RC-002 (Perf baseline manifest published for release window)

### Known Bottlenecks
- Dashboard/list paths sensitive to query shape and cardinality
- Search suggest sensitive to index health
- File APIs may degrade with slow object storage
- Async flows are queue/worker bound (may need job lifecycle tests)

---

## RB-005: E2E Diagnostics Closure

### Status
- Current: `missing`
- Target: `done`
- Workflow: `.github/workflows/e2e-smoke.yml`
- Tests: `frontend/e2e/smoke.spec.ts` + `tests/e2e/access/test_access_enforcement_matrix.py`

### Two-Stage Execution

#### Stage 1: Mandatory Smoke (No External Credentials)
Tests that always run (blocking):
- Login page renders
- Protected route redirects to login when logged out
- Unauthorized/denied route shows access denied page

Run: `npm run e2e -- --grep "mandatory (no external creds)"`

#### Stage 2: Credential Matrix Tests (Optional Secrets)
Tests that require credentials (runs if available):
- Owner user happy path (R11 login, documents list, navigation)
- Limited user deny path (student role denied on documents route)
- Error handling (wrong password, logout)

Credential sources:
1. **bootstrap_local** (always): Deterministic users created in CI job
   - Owner: `e2e.owner.demo@example.com` / `OwnerDemo123!`
   - Limited: `e2e.student.demo@example.com` / `StudentDemo123!`

2. **repo_secrets** (optional): External credentials from GitHub secrets
   - Requires: `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, `E2E_LIMITED_USER_EMAIL`, `E2E_LIMITED_USER_PASSWORD`

Run: `npm run e2e -- --grep "credential-based flows"`

### Backend Access Matrix Coverage

Tests validate both positive (allowed) and negative (denied) paths:

| Access rule | Positive test | Negative test |
|------------|---|---|
| Owner/admin broad in-tenant | `test_owner_can_do_everything_in_tenant` | `test_cross_tenant_write_is_rejected` |
| Auditor read-only | role map checks | `test_auditor_ro_cannot_create_or_update` |
| Student/instructor training | role permission map | `test_direct_api_create_is_denied_for_low_privilege_user` |
| Scope-based ABAC | `test_inspector_contractor_reads_within_contractor` | `test_hse_specialist_denied_on_foreign_company` |
| Cross-tenant deny | in-tenant success paths | `test_cross_tenant_header_is_denied_even_for_privileged_user` |
| File access deny | same-company download success | `test_file_detail_denies_client_from_other_company` |
| Session privilege reuse | fresh token success | `test_stale_admin_token_is_denied_after_role_downgrade` |

### Prerequisites
- Node.js 20
- Python 3.12
- `npm ci` in frontend/ directory
- Playwright browsers installed: `npx playwright install --with-deps chromium`
- SQLite dev.db or test database

### Run via GitHub Actions (Recommended)
1. Go to **Actions** tab
2. Select **"E2E smoke"** workflow
3. Click **"Run workflow"** → select **Main branch** → **"Run workflow"**
4. Wait for completion (~15–20 min, includes browser downloads and backend start)
5. Check workflow logs:
   - First job: "Minimal smoke (mandatory)" → should say "PASSED" for all mandatory tests
   - Second job: "Credential smoke (bootstrap_local)" → should pass access matrix tests
6. Verify: No failures or skipped tests

### Documentation
- Full guide: `docs/stabilization/e2e-access.md`
- Test file: `tests/e2e/access/test_access_enforcement_matrix.py`
- Mapped to: RC-006 (Secrets-dependent e2e diagnostics produce stable green artifact)

### Known Issues
- Playwright can be slow to download browsers on first run
- Backend startup can timeout if dependencies are slow (increase timeout if needed)
- Tests are somewhat flaky due to timing (retries are in place)

---

## Release Blockers Status Update Procedure

After running all three RB (RB-001, RB-002, RB-005) and verifying success:

### Step 1: Update `RELEASE_BLOCKERS_STATUS.md`

Find the checklist:
```markdown
- [ ] **RB-001 Restore drill closure** ...
- [ ] **RB-002 Perf baseline closure** ...
- [ ] **RB-005 Secrets-dependent e2e diagnostics closure** ...
```

Change to:
```markdown
- [x] **RB-001 Restore drill closure** ...
- [x] **RB-002 Perf baseline closure** ...
- [x] **RB-005 Secrets-dependent e2e diagnostics closure** ...
```

Also update "Updated on (UTC)" to current date.

### Step 2: Update `RELEASE_READINESS.md`

Sync the verdict table:
```markdown
| RC-001 | ... | `done` | ... |
| RC-002 | ... | `done` | ... |
| RC-006 | ... | `done` | ... |
```

Update "Launch readiness verdict":
```markdown
- **Verdict:** **READY** (all 6 blockers done)
- **Updated on (UTC):** 2026-04-30
```

### Step 3: Commit Changes

```bash
git add RELEASE_BLOCKERS_STATUS.md RELEASE_READINESS.md
git commit -m "release: RB-001, RB-002, RB-005 done — Release READY as of 2026-04-30

- RB-001 restore drill: accepted with success=true, checksums match
- RB-002 perf baseline: manifest published with all scenarios
- RB-005 e2e diagnostics: mandatory + credential matrix passed

Release blockers: 6/6 closed (RB-003 partial covered, RB-004 security done, RB-006 coverage done)

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

## Summary & Next Steps

| RB | Command/Method | Expected Artifact | Acceptance Criteria |
|----|---|---|---|
| **RB-001** | GitHub Actions manual dispatch | `latest-postgres-minio.json` | `success: true`, checksums match |
| **RB-002** | GitHub Actions manual dispatch | `trend-manifest.json` | Profile present, all results populated |
| **RB-005** | GitHub Actions manual dispatch | E2E test logs | All tests PASSED |

**Timeline:** ~45–60 minutes total (all 3 workflows in sequence)

**After completion:**
1. Update RELEASE_BLOCKERS_STATUS.md (mark RB-001/002/005 done)
2. Update RELEASE_READINESS.md (change verdict to READY)
3. Commit changes
4. Branch is ready for release
