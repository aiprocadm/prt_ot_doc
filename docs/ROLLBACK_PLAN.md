# ROLLBACK PLAN

## Rollback criteria
- Repeated P0 auth/tenant leakage
- Data corruption in document pipeline
- Unrecoverable queue failures impacting critical flows
- Sustained SLA breach without mitigation

## App rollback
1. Freeze traffic (maintenance mode / ingress switch).
2. Deploy previous stable image tag.
3. Keep readonly mode until smoke is green.

## DB rollback approach
- Prefer forward-fix migrations.
- If mandatory rollback: apply tested downgrade path for last release window only.
- Restore DB snapshot if downgrade unsafe.

## Feature-flag mitigation
- Disable non-critical modules (portal exports, advanced replace, optional webhooks) via flags.
- Keep core tenant/auth/docs flows active.

## Emergency tenant suspension
- Suspend impacted tenant in admin.
- Stop API token issuance for tenant.
- Preserve audit trail and snapshot affected records.

## Queue freeze procedures
- Freeze export/sign/EDO dispatch workers.
- Drain/park pending jobs.
- Resume only after fix verification.
