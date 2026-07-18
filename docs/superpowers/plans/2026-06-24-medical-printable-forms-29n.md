# Медосмотры §9.2 — финализация: печатные формы 29н + runtime hazard→factor CRUD

**Goal:** Close the two genuine remaining §9.2 gaps so the medical contour is operationally complete:
1. **Печатные формы 29н** — `контингент` (register) + `поименный список` (named-list) as downloadable **DOCX/PDF** (data is already computed by `build_contingent_register`/`build_named_list`; only the rendering layer is missing).
2. **Runtime hazard→factor mapping CRUD** — set `RiskHazard.medical_factor_code` via API (currently demo-seed / direct-field only), so tenants can configure factor-driven auto-contingent without DB surgery.

Out of scope (separate ТЗ chapters / contours, explicitly deferred by the specs): §9.1 budget/medorgs, §9.3 health-контур `[v1.2]`, §11.3 org-structure import, persistent snapshot/version table (stays live-compute), full 29н catalog (operational task).

**Branch:** `feat/medical-printable-forms-29n` off `origin/main`@`98bf49bf`.
**Env:** Win + `.venv` Py3.13.7 (canonical Py3.12.12 = CI, off — local-evidence). Tests via PowerShell→file, judge by EXIT code.

**Pattern mirrored (proven):** work-permit print — `services/work_permit_print.py` (`render_*` → `RenderedDoc`) → `domains/work_permits/print_form.py` (pure `python-docx` → `bytes`) → `modules/pdf/convert.py::convert_docx_bytes` (LibreOffice, `PdfRendererUnavailable`→503). Route: `Response` + `Content-Disposition: attachment; filename*=UTF-8''…`, `?format=docx|pdf` via `Literal` (invalid→422).

---

## Task 1 — Pure DOCX builders (`domains/medical/print_form.py`)
TDD: `backend/tests/test_medical_print_form.py`. Pure module (no I/O / no sqlalchemy), mirrors `work_permits/print_form.py`.
- RU vocab: `EXAM_KIND_LABELS` (periodic/preliminary/psychiatric/fluorography/health_book), `CONTINGENT_STATUS_LABELS` (ok/due_soon/overdue/missing). `exam_kind_label`/`contingent_status_label` fall back to the raw code.
- Dataclasses `RegisterPrintData`/`RegisterPrintRow`, `NamedListPrintData`/`NamedListPrintRow`.
- `build_contingent_register_docx(data) -> bytes`, `build_named_list_docx(data) -> bytes`. Empty rows → heading + "—" (no crash).

## Task 2 — Render service (`services/medical_print.py`)
TDD: `tests/test_medical_print_service.py` (DB-backed). Local `RenderedDoc` + `PdfRendererUnavailable` (decoupled, mirrors repo style).
- `render_contingent_register(session, *, tenant, fmt="docx") -> RenderedDoc`, `render_named_list(...)`. Map `medsvc.build_*` rows → print dataclasses → docx; `fmt=="pdf"` → `convert_docx_bytes` via `asyncio.to_thread`, failure→`PdfRendererUnavailable`. Always renders (empty tenant → empty doc).

## Task 3 — Print endpoints (`routes/medical.py`)
TDD: `tests/api/test_medical_print_api.py`.
- `GET /medical/contingent/register/print?format=` , `GET /medical/named-list/print?format=` — `MedicalFeatureGate` + `MedicalReadAccess`; `PdfRendererUnavailable`→503; `Response` w/ `Content-Disposition`. Invalid format→422; feature-off/cross-tenant→404.

## Task 4 — Runtime hazard→factor mapping (`routes/medical.py` + `schemas/medical.py`)
TDD: `tests/api/test_medical_hazard_factor_mapping.py`.
- Schemas `HazardFactorMappingIn{factor_code: str|None}`, `HazardFactorMappingRead`, `HazardFactorMappingPage`.
- `GET /medical/hazard-factors` (list tenant hazards + current mapping, read access).
- `PUT /medical/hazards/{hazard_id}/factor` (write access): hazard tenant-scoped→404; `factor_code` non-null must exist in tenant `MedicalFactor` catalog→422; set/clear field; audit `object_type="hazard_factor_mapping"`; commit.
- e2e: map a hazard → person on that position appears factor-driven in named-list/contingent.

## Task 5 — Regression + handoff
Medical cohort + adjacent (`migration|mapper|risk`) green; update `AI_IMPLEMENTATION_REPORT.md`.
