# RELEASE_READINESS

## Ready now
- Canonical roots and active entrypoints are documented.
- `frontend/package.json` is verified in the actual frontend root.
- Tenant/company/site branding inheritance works through the backend branding module.
- Header/footer requisites can be managed independently through `header_details` and `footer_details`.
- Branch-specific branded names are reflected in generated header/footer context.
- Wizard step 5 exposes branded preview, resolution chain, watermark diagnostics, and reproducibility snapshot.
- Branded preview metadata is durable across wizard navigation through the persisted wizard store.
- Backend tests and repo-local smoke checks cover the branding preview/apply-headers handoff.
- Repository audit output is reproducible and captures canonical entrypoints, config inventory, root expectations, and required docs coverage in Markdown and JSON form.
- Frontend production build emits predictable vendor chunks without the previous oversized main-bundle warning.
- Organization/branch branding screen now surfaces recent server-side branded generation history for audit/re-issuance.

## Conditional go-live checks
- Run backend/frontend verification commands from `README.md`.
- Validate one tenant end-to-end: company + site + preset + preview + generated DOCX + `apply-headers` smoke.
- Explicitly verify which production pipeline profiles auto-chain `apply_headers` and which require a separate step.
- Keep new ADRs under `docs/ADR/` and new approval work under `backend/app/modules/approvals/` until legacy duplicates can be retired safely.

## Additional readiness notes — 2026-03-21
- Notifications API is now materially closer to production boundaries: thin router, explicit service layer, structured enum validation, aggregate unread counts.
- Training/LMS and risk docs are now explicit enough for the next wave to continue from repo state without prompt memory.
