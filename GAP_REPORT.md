# GAP_REPORT

## Closed in this wave
- Revalidated canonical backend/frontend roots and active entrypoints.
- Reconfirmed `frontend/package.json` as the only active frontend manifest.
- Strengthened branding reproducibility with hashes for branding payload, header context, rendered sections, and preset content.
- Persisted branded preview/history inside the document wizard store, so operators do not lose preview context while moving through steps.
- Refreshed canonical repository docs to describe the real active paths and branded document flow.

## Remaining gaps
- Not every generation route automatically chains `generate -> apply_headers -> pdf`; some flows still require explicit `apply_headers` invocation or pipeline-profile configuration.
- Branding asset management still uses file IDs rather than a dedicated upload/media picker workflow on the branding screen.
- Preview history is persisted in frontend state, but not yet materialized as a server-side generation/audit projection.
