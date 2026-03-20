# PROJECT_STRUCTURE

## Canonical roots
- Backend: `backend/`
- Frontend: `frontend/`
- Infra and local orchestration: `infra/`, `docker-compose.yml`, `config/`
- Tests: `tests/`, `frontend/src/__tests__/`, `integration_tests/`
- Canonical docs: `docs/`

## Backend map
- `backend/app/main.py` — ASGI entrypoint.
- `backend/app/api/app.py` — FastAPI factory and middleware registration.
- `backend/app/api/v1/router.py` — canonical v1 router wiring.
- `backend/app/modules/branding/` — tenant/company/site branding profile and preview API.
- `backend/app/modules/headers/` — layout preset CRUD and DOCX header/footer application engine.
- `backend/app/api/routes/documents.py` — document generation entrypoints and batch routes.
- `backend/app/services/pipelines_orchestrator.py` — document job orchestration foundation.

## Frontend map
- `frontend/package.json` — canonical package manifest.
- `frontend/src/main.tsx` — React bootstrap.
- `frontend/src/router/AppRouter.tsx` — route tree.
- `frontend/src/pages/branding/BrandingSettingsPage.tsx` — branding/letterhead settings UX.
- `frontend/src/pages/documents/DocumentsWizardPage.tsx` — branded document generation wizard.
- `frontend/src/api/branding.ts` — branding API client.

## Structural audit notes
- The repository has a single active frontend manifest: `frontend/package.json`.
- `ptd` in the repo root is not a frontend directory; it is a small executable wrapper around `python -m app.cli.main`.
- Backend root is not the repository root; commands target `backend.app.*`, while legacy imports still use `app.*`.
- Repo root now contains `app/__init__.py`, a compatibility package exposing `backend/app` as top-level `app`, eliminating the broken import path for `python -m backend.app.main`.
- There are multiple historical docs folders/files; the files listed in README are the canonical operator-facing docs for the next task.
- `modules/approval` and `modules/approvals` both exist; they remain in place to avoid breaking active imports, but `api/routes/approval_*` remains the active router path.
