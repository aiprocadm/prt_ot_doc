# Release Blockers Execution Status (Wave 40)

**Last Updated:** 2026-04-30 (UTC)  
**Status:** ✅ **ALL 3 BLOCKERS READY FOR CI EXECUTION**

---

## Executive Summary

All three Release Blockers (RB-001, RB-002, RB-005) have been verified and are **READY FOR EXECUTION** in GitHub Actions. All necessary code, scripts, workflows, and tests are in place.

| Blocker | Name | Status | Execute Via |
|---------|------|--------|-------------|
| **RB-001** | Restore Drill (RTO/RPO validation) | ✅ READY | `.github/workflows/restore-drill.yml` |
| **RB-002** | Perf Baseline (performance manifest) | ✅ READY | `.github/workflows/perf-baseline.yml` |
| **RB-005** | E2E Diagnostics (access enforcement) | ✅ READY | `.github/workflows/e2e-smoke.yml` |

---

## RB-001: Restore Drill (Backup/Restore Validation)

### Status: ✅ READY

### What It Does
Validates backup and restore functionality for RTO/RPO (Recovery Time/Point Objective) compliance.

### Execution
**GitHub Actions UI:**
1. Go to Actions tab
2. Select "Restore Drill" workflow
3. Click "Run workflow" → Select main branch → Click "Run workflow"
4. Wait for completion (~5-10 min)

**Or via CLI:**
```bash
gh workflow run restore-drill.yml --ref main
```

### Expected Output
Artifact: `restore-drill-evidence/latest-{mode}.json`

**Acceptance Criteria (ALL must be true):**
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

### Test Modes
- **sqlite** (local): No external dependencies required
- **postgres-minio** (CI): Validates production-like backup/restore with PostgreSQL + MinIO

### Code Readiness
- ✅ Script: `scripts/restore_drill.py` — fully implemented
- ✅ Workflow: `.github/workflows/restore-drill.yml` — configured with PostgreSQL 16 + MinIO services
- ✅ CLI command: `python -m backend.app.cli.main health check --json` — verified working
- ✅ Database schema: All tables present and properly indexed
- ✅ Health endpoint: `/health` returns `{"status": "ok"}` with exit code 0

### Mapped To
- RC-001 (Restore drill acceptance criteria)
- RC-012 (RTO/RPO closure)

---

## RB-002: Perf Baseline (Performance Manifest)

### Status: ✅ READY

### What It Does
Generates baseline performance metrics for API endpoints under load testing.

### Execution
**GitHub Actions UI:**
1. Go to Actions tab
2. Select "Perf Baseline" workflow
3. Click "Run workflow" → Select main branch → Click "Run workflow"
4. Wait for completion (~10-15 min, includes Docker build)

**Or via CLI:**
```bash
gh workflow run perf-baseline.yml --ref main
```

### Expected Output
Artifacts:
- `artifacts/perf/nightly/trend-manifest.json` — consolidated results
- `artifacts/perf/nightly/summary.md` — markdown table
- `artifacts/perf/nightly/summary.csv` — CSV format

**Acceptance Criteria:**
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

### Endpoints Tested
1. `/health` — auth/session readiness
2. `/api/v1/dashboard/summary` — dashboard aggregate read
3. `/api/v1/templates` — list/read endpoint
4. `/api/v1/search/suggest?q=doc` — search latency
5. `/api/v1/documents/generate` — document generation flow
6. `/api/v1/files` — file operations

### Code Readiness
- ✅ Script: `scripts/perf/api_load.py` — load testing engine
- ✅ Scenarios: `scripts/perf/scenarios.json` — comprehensive endpoint profiles
- ✅ Workflow: `.github/workflows/perf-baseline.yml` — Docker Compose orchestration
- ✅ API endpoints: All required endpoints exist and return proper status codes
- ✅ Database seeding: Demo tenant bootstrapped with stable test data

### Mapped To
- RC-002 (Perf baseline manifest published for release window)

---

## RB-005: E2E Diagnostics (Access Enforcement)

### Status: ✅ READY

### What It Does
Validates end-to-end access enforcement, RBAC/ABAC policies, and frontend user flows.

### Execution
**GitHub Actions UI:**
1. Go to Actions tab
2. Select "E2E smoke" workflow
3. Click "Run workflow" → Select main branch → Click "Run workflow"
4. Wait for completion (~15-20 min, includes Playwright browser download + backend startup)

**Or via CLI:**
```bash
gh workflow run e2e-smoke.yml --ref main
```

### Execution Stages

#### Stage 1: Mandatory Smoke Tests (No credentials required)
Tests that always run (blocking):
- ✅ Login page renders
- ✅ Protected route redirects to login
- ✅ Unauthorized/denied route shows access denied page

Run pattern: `npm run e2e -- --grep "mandatory (no external creds)"`

#### Stage 2: Credential Matrix Tests (Bootstrap local credentials)
Tests that run with deterministic bootstrap users:
- ✅ Owner user login (R11)
- ✅ Owner documents list after login (R11)
- ✅ Navigation flows (command bar, top nav, mobile menu)
- ✅ Logout returns to login
- ✅ Backend access matrix enforcement (7 security rules)

Bootstrap credentials (generated in CI):
- Owner: `e2e.owner.demo@example.com` / `OwnerDemo123!`
- Limited: `e2e.student.demo@example.com` / `StudentDemo123!`

Run pattern: `npm run e2e -- --grep "credential-based flows"`

### Backend Access Matrix Coverage
| Access Rule | Positive Test | Negative Test |
|-------------|---|---|
| Owner/admin broad in-tenant | ✅ `test_owner_can_do_everything_in_tenant` | ✅ `test_cross_tenant_write_is_rejected` |
| Auditor read-only | ✅ role map checks | ✅ `test_auditor_ro_cannot_create_or_update` |
| Student/instructor training | ✅ role permission map | ✅ `test_direct_api_create_is_denied_for_low_privilege_user` |
| Scope-based ABAC | ✅ `test_inspector_contractor_reads_within_contractor` | ✅ `test_hse_specialist_denied_on_foreign_company` |
| Cross-tenant deny | ✅ in-tenant success paths | ✅ `test_cross_tenant_header_is_denied_even_for_privileged_user` |
| File access deny | ✅ same-company download success | ✅ `test_file_detail_denies_client_from_other_company` |
| Session privilege reuse | ✅ fresh token success | ✅ `test_stale_admin_token_is_denied_after_role_downgrade` |

### Code Readiness
- ✅ Frontend tests: `frontend/e2e/smoke.spec.ts` — Playwright tests with both mandatory + credential flows
- ✅ Backend tests: `backend/tests/e2e/access/test_access_enforcement_matrix.py` — comprehensive access rule validation (NEW, wave 40)
- ✅ Test helpers: `frontend/e2e/helpers/auth.ts` — login/logout utilities
- ✅ Playwright config: `frontend/playwright.config.ts` — proper setup for CI execution
- ✅ Backend lite: `scripts/run_backend_lite.py` — starts backend in CI with deterministic bootstrap
- ✅ Bootstrap script: `scripts/bootstrap_tenant.py` — creates test users and data
- ✅ Policy engine: `app.core.rbac_abac` — complete RBAC/ABAC implementation

### Mapped To
- RC-006 (Secrets-dependent e2e diagnostics produce stable green artifact)

---

## Execution Checklist

Before running, ensure:

- [ ] **GitHub CLI installed:** `gh --version`
- [ ] **GitHub authentication:** `gh auth status` (must show authenticated)
- [ ] **Sufficient API rate limit:** `gh api rate_limit`
- [ ] **Branch pushed:** `git push origin claude/happy-moser-4c4f02`
- [ ] **Workflows visible:** All 3 workflows appear in GitHub Actions tab

### Recommended Execution Order

1. **RB-001 (Restore Drill)** — Takes 5-10 minutes, validates backup/restore
   ```bash
   gh workflow run restore-drill.yml --ref main
   ```

2. **RB-002 (Perf Baseline)** — Takes 10-15 minutes, can run in parallel with RB-001
   ```bash
   gh workflow run perf-baseline.yml --ref main
   ```

3. **RB-005 (E2E Smoke)** — Takes 15-20 minutes, validates frontend + backend access
   ```bash
   gh workflow run e2e-smoke.yml --ref main
   ```

**Total time:** ~20-35 minutes (if parallelized)

---

## Success Criteria

All three blockers must meet their acceptance criteria:

| Blocker | Success Metric | Check |
|---------|---|---|
| RB-001 | Artifact has `"success": true` + all verifications pass | ✅ Artifact download + JSON inspection |
| RB-002 | Trend manifest with all endpoints + proper p50/p95/p99 values | ✅ Artifact download + metric validation |
| RB-005 | All tests PASSED (no failures, no skipped) | ✅ GitHub Actions workflow logs |

---

## Post-Execution Steps (After All 3 Pass)

1. **Download artifacts** from GitHub Actions (if needed for documentation)
2. **Update RELEASE_BLOCKERS_STATUS.md:**
   - Check RB-001, RB-002, RB-005
   - Update "Updated on (UTC)" to execution date

3. **Update RELEASE_READINESS.md:**
   ```markdown
   | RC-001 | Restore drill acceptance | `done` |
   | RC-002 | Perf baseline manifest | `done` |
   | RC-006 | E2E diagnostics | `done` |
   ```
   - Change verdict to: **READY** (all 6 blockers closed)

4. **Create release commit:**
   ```bash
   git commit -m "release: RB-001, RB-002, RB-005 verified — Release READY as of 2026-04-30
   
   - RB-001 restore drill: accepted with success=true
   - RB-002 perf baseline: manifest published with all metrics
   - RB-005 e2e diagnostics: all tests passed
   
   Release blockers: 6/6 closed
   Verdict: READY for release
   
   Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
   ```

5. **Push to main (after review):**
   ```bash
   git push origin main
   ```

---

## Known Limitations & Considerations

### RB-001 (Restore Drill)
- ⚠️ Postgres mode requires pg_dump/pg_restore CLI tools (installed in CI)
- ⚠️ First MinIO interaction may be slow (bucket creation)
- ✅ SQLite mode needs no external dependencies, perfect for smoke tests

### RB-002 (Perf Baseline)
- ⚠️ Results depend on stable demo data (use clean DB snapshot)
- ⚠️ Performance sensitive to:
  - Database cardinality (list/search endpoint query shape)
  - Search index health
  - File storage backend (local vs S3)
  - Async job queue capacity

### RB-005 (E2E)
- ⚠️ Playwright browsers slow to download on first run (~2-3 min)
- ⚠️ Backend startup can timeout if dependencies slow (increase if needed)
- ⚠️ Tests somewhat flaky due to timing (retries are in place)
- ✅ Mandatory smoke tests always run (no credentials needed)
- ✅ Credential tests require bootstrap users (auto-created in CI)

---

## References

- [Wave 37 RB Guide](./wave-37-rb-guide.md) — Detailed execution instructions
- [Release Blockers Status](./RELEASE_BLOCKERS_STATUS.md) — Official blocker checklist
- [Release Readiness](./RELEASE_READINESS.md) — Release verdict and RC matrix
- [Restore Drill Docs](./docs/stabilization/restore-drill.md) — Detailed restore drill theory
- [E2E Access Docs](./docs/stabilization/e2e-access.md) — E2E test matrix documentation

---

## Sign-Off

**Generated:** 2026-04-30 (UTC)  
**Verified By:** Claude (Wave 40)  
**Status:** ✅ Ready for Release Manager to Execute

All systems verified. RB blockers are green-light ready for GitHub Actions execution.
