# DOCUMENT_CORE

## Canonical pipeline
`Template -> branding profile -> layout preset -> rendered preview -> apply headers -> PDF -> approval/sign/archive`

## Implemented building blocks
- tenant/company/site branding inheritance;
- first / odd / even header and footer sections;
- placeholder rendering with unresolved-placeholder reporting;
- watermark resolution from preset + profile + request override;
- reproducibility metadata for branding payload, header context, rendered sections, preset content, and entity timestamps;
- async idempotent header application endpoint and Celery job;
- frontend wizard handoff using backend-returned `apply_headers_payload`.

## Fast branded generation scenario
1. Operator selects organization and optional branch.
2. System resolves brand profile and preferred preset.
3. Wizard or branding screen calls `/api/v1/branding/preview`.
4. Preview returns rendered sections plus reproducibility metadata.
5. Wizard persists the preview locally so the operator can move across steps without losing the branded context.
6. Generated DOCX can be sent to `apply-headers` with the exact preview context.

## Current boundary
Preview preparation and apply-headers handoff are production-ready. Some generation profiles still require explicit chaining of `apply_headers` after DOCX creation rather than automatic inline chaining in every flow.
