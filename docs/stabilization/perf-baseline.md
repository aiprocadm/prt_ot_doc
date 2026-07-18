# Performance Baseline (Stabilization)

_Last updated: 2026-04-20 (expanded scenarios + threshold policy)._

This document defines the implemented critical flows, deterministic harness inputs, CI perf smoke thresholds, and scheduled baseline collection strategy.

## 1) Implemented critical flows (stabilization scope)

The following flows are implemented and covered by a combination of API load probes plus existing integration tests:

| # | Critical flow | Probe/Test mapping | Notes |
|---|---|---|---|
| 1 | Auth/session readiness (token refresh prerequisite) | `GET /health` load probe | Availability guard used by PR perf smoke. |
| 2 | Dashboard load | `GET /api/v1/dashboard/summary` load probe | Representative aggregate read path. |
| 3 | List + browse | `GET /api/v1/templates` load probe | Main list/read endpoint profile. |
| 4 | Search suggest | `GET /api/v1/search/suggest?q=doc` load probe | Search latency sensitivity path. |
| 5 | Create/update pipeline | `tests/integration/test_pipeline_steps_happy_path.py`, `tests/integration/test_pipeline_idempotency.py` | Correctness-backed write flow; extend with dedicated write perf later. |
| 6 | Document generate + apply-headers | Multi-step flow probe (`POST /api/v1/documents/generate` + `POST /api/v1/headers/documents/{id}/apply-headers`) | Added to nightly profile with idempotency keys. |
| 7 | Files upload-init/finalize/download-url | Multi-step flow probe (`POST /api/v1/files:upload-init` → `POST /api/v1/files/{id}:finalize` → `POST /api/v1/files/{id}:download-url`) | Covers hot file upload/read URL path beyond simple list/read probe. |
| 8 | Jobs status transitions | Multi-step flow probe (`POST /api/v1/jobs` → `GET /api/v1/jobs/{id}` → `POST /api/v1/jobs/{id}:cancel` → `POST /api/v1/jobs/{id}:retry`) | Adds lifecycle responsiveness measurement for async jobs API. |

## 2) Deterministic perf harness inputs

Canonical inputs are defined in `scripts/perf/scenarios.json`.

Dataset assumptions:

- Tenant: `demo`.
- Seed model: stable demo corpus/templates.
- Run condition: clean DB snapshot before each baseline capture.

Fixed load profile inputs:

- **PR smoke profile** (fast gate): requests 60–80, concurrency 12–16.
- **Nightly baseline profile** (trend): requests 120–200, concurrency 12–20.

These fixed inputs avoid drift from ad-hoc parameter changes and keep trend comparisons meaningful.

## 3) PR smoke performance gate (CI)

`.github/workflows/ci.yml` now includes a `perf-smoke` job that:

- Brings up the stack with Docker Compose.
- Runs `scripts/perf/api_load.py` against top read endpoints.
- Enforces explicit threshold pass/fail criteria.
- Uploads JSON perf artifacts for each scenario.

### PR smoke explicit thresholds

| Endpoint | Requests | Concurrency | p95 max (ms) | p99 max (ms) | Throughput min (rps) | Error-rate max |
|---|---:|---:|---:|---:|---:|---:|
| `/health` | 80 | 16 | 250 | 600 | 30 | 2.0% |
| `/api/v1/dashboard/summary` | 60 | 12 | 600 | 1200 | 15 | 2.0% |
| `/api/v1/templates` | 60 | 12 | 500 | 1000 | 18 | 2.0% |
| `/api/v1/search/suggest?q=doc` | 60 | 12 | 450 | 900 | 18 | 2.0% |

## 4) Scheduled fuller baseline workflow

New workflow: `.github/workflows/perf-baseline.yml`

Schedule:

- Nightly at `03:00 UTC`.
- Manual trigger (`workflow_dispatch`) for ad-hoc baselines.

Behavior:

- Runs the fuller baseline profile directly from `scripts/perf/scenarios.json`, including new multi-step flow probes.
- Stores per-endpoint JSON summaries in `artifacts/perf/nightly/`.
- Produces `trend-manifest.json` to consolidate run metadata/results.
- Produces `summary.md` and `summary.csv` with p50/p95/p99/error-rate/throughput for every scenario.
- Uploads artifacts per run (`perf-baseline-${run_id}`) for trend review.

## 5) Before/After baseline coverage

### Before (until 2026-04-19)

- Read-heavy nightly profile only:
  - `/health`
  - `/api/v1/dashboard/summary`
  - `/api/v1/templates`
  - `/api/v1/search/suggest?q=doc`
  - `/api/v1/files`
- Artifact shape: per-scenario JSON + `trend-manifest.json`.

### After (from 2026-04-20)

- Nightly profile includes previous read probes **plus**:
  - `document_generate_apply_headers` (flow probe, idempotency aware),
  - `files_upload_flow` (upload-init/finalize/download-url),
  - `jobs_status_transitions` (status lifecycle probe).
- Artifact shape expanded with rollups:
  - per-scenario JSON,
  - `trend-manifest.json`,
  - `summary.md` + `summary.csv` (p50/p95/p99/error-rate/throughput).

### Trim (from 2026-05-29 — RB-002 caveat resolution)

The 3 FLOW probes above were removed from `scripts/perf/scenarios.json` because they reference literal entity IDs (`company_id=demo-company`, `person_id=demo-person`, `document_version_id=demo-document-version-id`, `template_code=Greeting`/`TMP`) that `bootstrap_demo_tenant` does not seed — bootstrap creates entities with auto-generated UUIDs, so the FLOW POST bodies never resolved to real targets. CI runs of the FLOW probes failed before the first response.

`nightly_baseline` is now pure-GET only (5 scenarios: `health`, `dashboard`, `templates_list`, `search_suggest`, `download_file`).

To re-introduce FLOW probes, pick one:
- (a) Extend `bootstrap_demo_tenant` to seed entities with literal IDs (e.g. `Company(id="demo-company")`) plus a `Template(code="Greeting")` + `TemplateVersion(version=1)` + a stable `DocumentVersion(id="demo-document-version-id")`.
- (b) Parameterize `scenarios.json` to discover seeded entities at probe-time via a pre-flight lookup (`GET /api/v1/companies?slug=demo` → capture id, then substitute).

## 6) Threshold policy

Policy levels:

1. **PR smoke (blocking gate):**
   - Enforces explicit max p95/p99, min throughput, and max error-rate per endpoint.
   - Any threshold violation fails CI immediately.
2. **Nightly baseline (trend gate):**
   - Always captures full profile artifacts.
   - Regression policy:
     - warning if p95 increases by >20% vs rolling 7-run median,
     - action required if p95 increases by >35% or error-rate >2.0% for two consecutive nightly runs,
     - action required if throughput drops by >25% vs rolling 7-run median.
3. **Flow probes (write/async paths):**
   - Threshold checks apply to whole-flow latency and status success.
   - Idempotency keys are required on steps that mutate state.

## 7) Baseline numbers + bottleneck notes

The initial baseline contract (used by CI gate and nightly trend) tracks:

- Latency: `p50`, `p95`, `p99`.
- Throughput: requests/second.
- Error-rate: failed requests / attempted requests.

### Current baseline contract values

| Endpoint | p50 target (ms) | p95 target (ms) | p99 target (ms) | Throughput target (rps) | Error-rate target |
|---|---:|---:|---:|---:|---:|
| `/health` | <= 150 | <= 250 | <= 600 | >= 30 | <= 2.0% |
| `/api/v1/dashboard/summary` | <= 300 | <= 600 | <= 1200 | >= 15 | <= 2.0% |
| `/api/v1/templates` | <= 250 | <= 500 | <= 1000 | >= 18 | <= 2.0% |
| `/api/v1/search/suggest?q=doc` | <= 225 | <= 450 | <= 900 | >= 18 | <= 2.0% |
| `/api/v1/files` (nightly) | <= 350 | <= 700 | <= 1400 | >= 12 | <= 2.0% |

### Bottleneck notes (known/expected)

1. **Dashboard and list aggregation paths** are sensitive to query shape/cardinality and may surface N+1 joins under expanded tenant datasets.
2. **Search suggest** is latency-sensitive to index health and wildcard usage.
3. **File APIs** often include storage metadata checks; throughput can degrade with slow backing object store/network.
4. **Async trigger flows** are typically queue/worker bound; API p95 may stay healthy while end-to-end completion degrades, so pair perf probes with job lifecycle integration tests.

## 8) Implementation references

- Load probe script: `scripts/perf/api_load.py`
- Deterministic profile inputs: `scripts/perf/scenarios.json`
- Probe usage notes: `scripts/perf/README.md`
- PR smoke perf gate: `.github/workflows/ci.yml`
- Nightly baseline workflow: `.github/workflows/perf-baseline.yml`
