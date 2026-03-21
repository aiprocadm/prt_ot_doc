# GAP_REPORT

## Closed / reduced in this wave
- Template DTO and frontend contract mismatch reduced by exposing scope/type/current-version/version-history more explicitly.
- Custom template catalog now carries canonical scope metadata for tenant / organization / branch(site) usage.
- Repo now documents demo access, owner bootstrap, and user role issuance explicitly.

## Remaining gaps
- Full automatic template override resolution at generation time is not yet fully centralized; operators still choose the final template/version explicitly.
- Branch naming in product language maps to backend `Site`, which should remain documented in future changes.
