# GAP_REPORT

## Closed in this wave
- Нормализован template catalog contract: `category`, `status`, `scope`.
- Исправлена связка upload version -> `current_version_id`.
- Снижен риск broken generation из-за рассинхрона `Template.code` vs `Template.name`.
- Repo теперь документирует demo access, owner/admin access и user access issuance.

## Remaining gaps
- Scope пока хранится в `metadata_json`, а не в отдельных indexed columns.
- Branch-specific generation опирается на текущую модель `Site`; отдельной branch-сущности нет.
- Полный automatic pipeline chain между всеми document entrypoints ещё не унифицирован.
- Version diff / richer preview / archive action UX остаются следующей волной hardening.
- Not every generation route automatically chains `generate -> apply_headers -> pdf`; some flows still require explicit `apply_headers` invocation or pipeline-profile configuration.
- Branding asset management still uses file IDs rather than a dedicated upload/media picker workflow on the branding screen.
- Preview history is persisted in frontend state, but not yet materialized as a server-side generation/audit projection.
- Duplicate legacy path pairs still remain on disk (`docs/ADR` vs `docs/adr`, `modules/approval` vs `modules/approvals`) and are documented rather than physically merged in this wave to avoid risky breakage.

## Additional gaps review — 2026-03-21
### Closed
- Fat-router notification logic was moved into a dedicated application module with reusable schemas/service boundaries.
- Invalid notification enum filters no longer rely on raw enum casting behavior.
- Malformed notification cursors and unsupported calendar sources now fail with the same structured 422 contract instead of producing generic failures or ambiguous empty feeds.
- Training/LMS and risk-engine documentation now clearly state their true maturity and canonical code paths.

### Remaining
- Notification preferences exist, but escalation policies and richer delivery providers are still foundation-level rather than fully orchestrated.
- Calendar aggregation is centralized, but not every deadline-bearing module is yet projected into the common feed.
## Closed / reduced in this wave
- Template DTO and frontend contract mismatch reduced by exposing scope/type/current-version/version-history more explicitly.
- Custom template catalog now carries canonical scope metadata for tenant / organization / branch(site) usage.
- Repo now documents demo access, owner bootstrap, and user role issuance explicitly.

## Remaining gaps
- Full automatic template override resolution at generation time is not yet fully centralized; operators still choose the final template/version explicitly.
- Branch naming in product language maps to backend `Site`, which should remain documented in future changes.
