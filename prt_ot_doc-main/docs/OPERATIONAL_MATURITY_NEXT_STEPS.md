# Operational Maturity Next Steps

## Immediate next wave (recommended)

1. Consistency hardening in critical orchestration APIs
- Focus files:
  - backend/app/api/routes/approval_signing_v1.py
  - backend/app/api/routes/approval_orchestration.py
  - backend/app/api/routes/edo_workflow.py
- Objectives:
  - uniform tenant checks
  - uniform permission enforcement (read/write/action)
  - uniform structured errors
  - correlation-id in all responses and async handoff points
  - complete audit for sensitive actions

2. Replace avoidable deferred/stub behavior with internal orchestration
- Keep provider abstraction stable.
- Do not imitate production external operators.
- Ensure truthful provider mode diagnostics, retries, statuses and audit trail.

3. Expand role workspaces and attention/task integration
- Make attention/task/blocker/next-action an obvious default user entry point.
- Add deep links and scenario-first recommendations.

4. Data quality integration into daily flow
- Persist issues by severity.
- Link issues to readiness and blockers in workspaces/dashboards.

5. PWA field hardening
- strengthen bootstrap contracts where needed
- improve queue/conflict/retry diagnostics and UX loops
- validate selected field scenarios end-to-end

## Testing gates for each slice

Required test bundles after each major slice:
- backend unit tests for tenant/authz/error contracts
- backend integration tests for orchestration transitions and provider mode signaling
- frontend tests for operational cockpit behavior and fallback states
- contract tests for readiness/attention/task projections

## Documentation gates for each slice

Update after each delivered slice:
- docs/OPERATIONAL_MATURITY_COMPLETION_REPORT.md
- docs/OPERATIONAL_MATURITY_REMAINING_GAPS.md
- docs/OPERATIONAL_MATURITY_NEXT_STEPS.md

## Exit criteria for enterprise-usable state

- Non-production provider modes are explicit and operationally visible.
- Critical orchestration flows are internally reliable with clear statuses, retries and diagnostics.
- Users can immediately understand overdue/blocked/next actions after login.
- Data quality blockers are first-class operational objects tied to readiness.
- Tenant/authz/error/audit/correlation behavior is consistent in all critical workflows.
