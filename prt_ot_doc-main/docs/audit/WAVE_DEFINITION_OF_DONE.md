# Wave Definition Of Done

This file defines mandatory completion gates for each implementation wave.

## Global DoD (all waves)

- Code changes merged with backward-compatible API behavior unless explicitly versioned.
- Unit/integration tests added or updated for the changed behavior.
- Error contract preserved: `code`, `type`, `message`, `details`, `field_errors`, `correlation_id`, `timestamp`.
- Correlation id propagated through API and async jobs where applicable.
- Audit coverage updated for critical business actions.
- Documentation updated in `docs/` and `docs/audit/`.

## Wave 0 (Baseline)

- `TZ_COVERAGE_MATRIX.md` contains wave/priority/status for every major TZ contour.
- Acceptance linkage documented in `ACCEPTANCE_TEST_MATRIX.md`.
- Top unresolved P0/P1 gaps are explicitly listed.

## Wave 1 (Platform Core)

- Tenant context enforced for all non-public business routes.
- RBAC/ABAC checks are consistent for critical modules.
- Reliability tasks include cleanup/retry/poison handling and stuck job watchdog.
- Structured auth/tenancy failures are covered by tests.

## Wave 2 (Document Core)

- Document pipeline supports deterministic path from generation to artifacts.
- Readiness score exposes blockers and recommended actions.
- Pipeline retries and failed-stage restart behavior is tested.

## Wave 3 (Domain Completion)

- Risks/PPE/Training/Incidents/Inspections lifecycle paths are connected by rules/tasks.
- Cross-domain updates produce timeline/attention signals.

## Wave 4 (Frontend + Mobile/Offline)

- Role workspaces expose priority KPIs/actions without critical screen overload.
- Offline queue/sync/conflict states are visible and actionable.
- Command-driven navigation and search workflows are available.

## Wave 5 (Integrations/EDO/Signatures)

- Stub providers are replaced by production adapters in selected environments.
- Webhook integrity (signature, dedup, replay protection) is validated.
- Delivery status and retries are observable and auditable.
