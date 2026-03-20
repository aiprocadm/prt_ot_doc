# GAP_REPORT

## Closed in this wave
- Revalidated canonical backend/frontend roots and active entrypoints.
- Reconfirmed `frontend/package.json` as the only active frontend manifest.
- Added explicit `header_details` support to the branding profile so organization requisites can be managed separately for header and footer layouts.
- Fixed branch/site branding resolution so overridden `branch_label` is carried into previewed and generated headers.
- Strengthened branding reproducibility with hashes for branding payload, header context, rendered sections, and preset content.
- Persisted branded preview/history inside the document wizard store, so operators do not lose preview context while moving through steps.
- Added a dedicated `scripts/branded_document_smoke.py` smoke command and `make branded-smoke` entrypoint for fast verification of the canonical letterhead pipeline.
- Refreshed canonical repository docs to describe the real active paths and branded document flow.

## Remaining gaps
- Not every generation route automatically chains `generate -> apply_headers -> pdf`; some flows still require explicit `apply_headers` invocation or pipeline-profile configuration.
- Branding asset management still uses file IDs rather than a dedicated upload/media picker workflow on the branding screen.
- Preview history is persisted in frontend state, but not yet materialized as a server-side generation/audit projection.
