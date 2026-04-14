# Word Module Gap Matrix

## Baseline coverage

| Requirement area | Current implementation | Status | Main code anchors |
| --- | --- | --- | --- |
| Template registry and versioning | Template and template version models, upload/lint/preview endpoints | partial | `backend/app/modules/templates`, `frontend/src/api/templates.ts` |
| Placeholder rendering (`{{ }}`, `{% if %}`, `{% for %}`) | DOCX rendering through docxtpl/Jinja with strict mode fallback | implemented | `backend/app/domains/templating/renderer.py`, `backend/app/services/docx.py` |
| Mass replace + dry-run/apply/rollback | Replace maps, run reports, rollback endpoint | partial | `backend/app/modules/replace` |
| Pipeline orchestration | Graph/steps/job orchestration and retries | implemented | `backend/app/modules/pipelines`, `backend/app/services/pipelines_orchestrator.py` |
| Document passport | Embedded passport in generated docx metadata and visible block | implemented | `backend/app/modules/doc_render/passport.py`, `backend/app/modules/templates/passport.py` |
| Wizard UX | Step-by-step flow with source/mapping/template/replace/run/result/export/archive | partial | `frontend/src/pages/documents/wizard` |
| Batch generation | Batch upload, per-row runs, statuses, retry foundation | partial | `backend/app/api/routes/documents.py`, `frontend/src/api/documents.ts` |

## MVP target gaps

| Gap | Why it matters | Planned implementation |
| --- | --- | --- |
| Replace flags are not fully enforced (`regex`, granular `scope`) | Functional mismatch between UI contract and actual replace behavior | Upgrade replace engine usage and pass options end-to-end |
| No dedicated quality gate stage before release | Cannot reliably block release on critical data/render issues | Add `quality_gate` step and typed quality report contract |
| Missing unified stage/error contract for BE/FE | Inconsistent statuses and weak machine-readable error handling | Add shared stage/severity/error-code DTOs and wire to responses |
| Data mapping validation is basic | Users can start generation with incomplete required mappings | Add mapping validation endpoint with required-field checks |
| Approval/sign/EDO stages are not aligned as explicit release workflow | Harder to trace release lifecycle in one pipeline | Extend pipeline step vocabulary and readiness metadata |
| Search/filter completeness for document metadata is limited | Weak discoverability at scale | Extend filtering/search contracts and surface quality metadata |

## Delivery strategy

1. Stabilize contracts (`stage`, `severity`, `code`, `details`).
2. Add quality gate to block release on critical findings.
3. Ensure replace dry-run/apply parity with regex/scope behavior.
4. Introduce mapping validation for required fields before run.
5. Extend workflow steps and readiness metadata for release lifecycle.
