# ACCEPTANCE_TEST_MATRIX

| Scenario | Status | Canonical code/docs |
|---|---|---|
| Owner bootstrap | implemented | `scripts/bootstrap_tenant.py`, `docs/OWNER_ADMIN_ACCESS.md` |
| Demo bootstrap | implemented | `scripts/bootstrap_demo_tenant.py`, `docs/DEMO_ACCESS.md` |
| Custom template catalog card | implemented | `backend/app/api/v1/router.py`, `frontend/src/features/templates/TemplateFormDialog.tsx` |
| Template version upload + lint + preview | implemented foundation | `backend/app/api/v1/router.py`, `frontend/src/features/templates/TemplateDetails.tsx` |
| Org/branch-scoped template metadata | implemented foundation | `backend/app/api/v1/router.py`, `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Org-specific document generation | implemented foundation | `backend/app/api/routes/documents.py` |
