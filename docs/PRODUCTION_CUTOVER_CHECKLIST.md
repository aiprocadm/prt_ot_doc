# PRODUCTION CUTOVER CHECKLIST

## Pre-cutover
- [ ] Env vars complete and validated (`.env`, secrets store)
- [ ] Secrets provisioned (DB/Redis/S3/JWT/webhooks)
- [ ] DB migrations applied (`alembic upgrade heads`)
- [ ] Seed/reference data loaded (tenant/plans/presets/NPA)
- [ ] Quotas and billing plans loaded
- [ ] Storage buckets/prefixes and lifecycle policies configured
- [ ] Workers/celery/queues up
- [ ] `healthz` / `readyz` green
- [ ] Backup schedule configured
- [ ] Restore test passed (latest rehearsal)
- [ ] Alert channels connected
- [ ] Admin bootstrap complete

## Smoke after cutover
- [ ] Sample render works
- [ ] Sample PDF conversion works
- [ ] Sample export works
- [ ] Sample webhook ingestion works
- [ ] Tenant isolation spot-check passed
- [ ] Portal restricted user spot-check passed

## Go/No-Go
- [ ] Blockers = 0
- [ ] Critical known issues accepted with mitigation
- [ ] Stakeholders signoff recorded
