# RELEASE_READINESS

## Ready
- Canonical roots and entrypoints are documented.
- Frontend package manifest is verified in `frontend/`.
- Branding profile preview is tenant/company/site aware.
- Wizard now exposes branded preview before generation.
- Backend and frontend regression coverage added for branding preview handoff.

## Conditional go-live criteria
- Run backend/frontend test and build commands from README.
- Validate one tenant with company + site + layout preset + branded preview + apply-headers smoke.
- Confirm chosen pipeline profile for production explicitly chains `apply_headers` where required.
