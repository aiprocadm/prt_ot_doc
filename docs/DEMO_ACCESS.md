# DEMO_ACCESS

## Canonical demo bootstrap
Demo data is provisioned by:
- env flags: `DEMO_BOOTSTRAP`, `DEMO_TENANT_ID`, `DEMO_COMPANY_NAME`, `DEMO_SITE_NAME`;
- startup hook in `backend/app/api/app.py`;
- script:

```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_demo_tenant.py --force
```

Implementation:
- `scripts/bootstrap_demo_tenant.py`
- `backend/app/services/demo_bootstrap.py`

## Demo tenant meaning
- default demo tenant slug: `demo`;
- intended for walkthroughs, smoke checks and local/stage validation;
- branch/facility is represented in code by `Site`.

## What demo bootstrap creates
- tenant;
- demo company;
- demo site/branch;
- baseline org/person/training entities;
- starter packs and sample records used by walkthroughs.

## Login pattern
- API login route: `POST /api/v1/auth/login`
- Frontend: standard login page
- Always pass/select `X-Tenant: demo` or the configured demo slug.

## Credentials
Static demo credentials are **not stored in git**.

Safe ways to provision demo login:
1. create a dedicated demo owner via `scripts/bootstrap_tenant.py --demo`; or
2. bootstrap demo tenant data and then create a user through the owner/admin flow.

## Demo limitations
- synthetic data only;
- not a production provisioning flow;
- some integrations still require external secrets and separate enablement;
- some verticals are seeded more deeply than others.

## Demo-friendly modules
- templates and document generation;
- company/site-scoped branding and headers;
- packs;
- training foundation;
- incidents / inspections / risks baseline screens;
- audit-backed admin flows.
