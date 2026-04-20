# Performance Baseline (Stabilization)

_Last updated: 2026-04-20._

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
| 6 | File upload/download readiness | `GET /api/v1/files` load probe + file API tests | Read-side performance proxy + existing file correctness tests. |
| 7 | Async trigger/job status | `tests/integration/test_job_status_flow.py` | Ensures queue-backed trigger observability; pair with perf probe for API responsiveness. |

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

- Runs the fuller baseline profile (health, dashboard, list, search, files).
- Stores per-endpoint JSON summaries in `artifacts/perf/nightly/`.
- Produces `trend-manifest.json` to consolidate run metadata/results.
- Uploads artifacts per run (`perf-baseline-${run_id}`) for trend review.

## 5) Baseline numbers + bottleneck notes

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

## 6) Implementation references

- Load probe script: `scripts/perf/api_load.py`
- Deterministic profile inputs: `scripts/perf/scenarios.json`
- Probe usage notes: `scripts/perf/README.md`
- PR smoke perf gate: `.github/workflows/ci.yml`
- Nightly baseline workflow: `.github/workflows/perf-baseline.yml`
