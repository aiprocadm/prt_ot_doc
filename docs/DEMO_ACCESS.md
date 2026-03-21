# DEMO_ACCESS

## Demo tenant purpose
The repository contains a deterministic demo tenant intended for walkthroughs, smoke checks and local/stage validation of document workflows.

## Canonical bootstrap
```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_demo_tenant.py --force
```

## What demo bootstrap creates
- tenant slug from `Settings.demo_tenant_id` (default demo)
- demo company
- demo site/branch (`Site` model)
- baseline employee/course entities
- default starter packs and demo-like records used in walkthroughs

Implementation: `scripts/bootstrap_demo_tenant.py`, `backend/app/services/demo_bootstrap.py`.

## Login / route pattern
Auth is tenant-aware. Use the regular login route and pass/select the demo tenant slug configured for the environment.

- API login route: `/api/v1/auth/login`
- Frontend login screen: standard app login page
- Demo tenant slug: environment-driven (`demo` by default)

## Credentials
Static demo credentials are **not stored in git**.
Use one of these safe options:
1. bootstrap a dedicated owner account with `scripts/bootstrap_tenant.py --demo`; or
2. provision a demo user through the regular admin/owner flow in the demo tenant.

## Demo limitations
- intended for non-production data only;
- data is synthetic / seeded;
- branch is represented as `Site` in code;
- some external integrations require separate secrets and are not auto-enabled by demo bootstrap.

## Demo-enabled modules
The demo tenant is suitable for showing at least:
- templates and document generation;
- company/site-scoped branding;
- packs;
- training foundation;
- incidents / inspections / risks baseline screens;
- audit-backed admin flows already present in the tenant.
