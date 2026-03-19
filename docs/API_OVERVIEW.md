# API overview

## Public API prefix
`/api/v1`

## Canonical endpoints for this wave
- `/companies`
- `/sites`
- `/layout-presets`
- `/branding/profile`
- `/branding/preview`
- `/documents/*`
- `/pipelines/*`
- `/files/*`

## Important contracts
- Branding profile is tenant-aware and may be requested for company scope or company+site scope.
- Branding preview returns rendered sections, unresolved placeholders, resolved watermark and reproducibility metadata.
- Layout preset management is CRUD-like through `/layout-presets`.
- `apply-headers` is asynchronous and idempotent.
