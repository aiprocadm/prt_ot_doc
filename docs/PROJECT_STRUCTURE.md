# PROJECT_STRUCTURE

## Canonical roots
- **Backend:** `backend/`
- **Frontend:** `frontend/`
- **Tests:** `tests/`, `frontend/src/__tests__/`, `integration_tests/`
- **Infrastructure:** `infra/`, `docker-compose.yml`, `config/`
- **Canonical operator docs:** `README.md` and the documents listed below in `docs/`

## Backend canonical map
- `backend/app/main.py` — ASGI entrypoint.
- `backend/app/api/app.py` — FastAPI app factory.
- `backend/app/api/v1/router.py` — v1 router composition.
- `backend/app/modules/branding/` — brand profile inheritance, preview, reproducibility context.
- `backend/app/modules/headers/` — layout preset CRUD and DOCX header/footer application.
- `backend/app/api/routes/documents.py` — document generation and batch entrypoints.
- `backend/app/tasks.py` — async orchestration, including `apply_headers_job`.

## Frontend canonical map
- `frontend/package.json` — single active package manifest.
- `frontend/vite.config.ts` — Vite root config.
- `frontend/src/main.tsx` — React bootstrap.
- `frontend/src/router/AppRouter.tsx` — route tree.
- `frontend/src/pages/branding/BrandingSettingsPage.tsx` — branding settings and preview.
- `frontend/src/pages/documents/DocumentsWizardPage.tsx` — generation wizard with branded preview.
- `frontend/src/stores/documentsWizard.ts` — persisted wizard state, including branding preview history.

## Supporting operator/tooling paths
- `scripts/branded_document_smoke.py` — smoke check for firm-letterhead resolution and DOCX header/footer application without needing the full UI flow.
- `Makefile` target `branded-smoke` — canonical shell entry for the same smoke check.
- `scripts/smoke.sh` — broader repo smoke covering migrations/readiness/basic API probes.
- `scripts/repo_audit.py` — reproducible repository inventory for roots/manifests/configs/docs/legacy-path flags, writing both `docs/audit/REPOSITORY_AUDIT.md` and `docs/audit/REPOSITORY_AUDIT.json`.
- `Makefile` target `branded-smoke` — canonical shell entry for the same smoke check.
- `scripts/smoke.sh` — broader repo smoke covering migrations/readiness/basic API probes.
- `backend/.env.example` and `.env.example` — mirrored baseline environment templates; keep them aligned with `docs/SETUP.md` and `docs/ENV_REFERENCE.md`.

## Structural audit conclusions
- `frontend/package.json` is the **only** active frontend manifest.
- `app/__init__.py` is a repo-root compatibility shim exposing `backend/app` as top-level `app` for legacy imports and entrypoints.
- Historical parallel names still exist in a few areas (`docs/ADR` + `docs/adr`, `modules/approval` + `modules/approvals`). Canonical active paths are documented above; legacy paths remain only for backward compatibility and should not be used for new work.
- Canonical workflow/event and observability references now live in `docs/WORKFLOWS_AND_EVENTS.md` and `docs/OBSERVABILITY.md`.
- The repository audit now records root expectations, canonical layout sections, unexpected extra manifests, and README/docs index alignment so accidental structural drift is visible in both human-readable and machine-readable outputs.
- Canonical testing documentation now lives in `docs/TESTING.md`; lowercase `docs/testing.md` remains only as a backward-compatible pointer.
- There is no separate frontend hidden under `ptd`, `proxy`, or repo root.
