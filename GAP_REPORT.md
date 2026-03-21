# GAP_REPORT

## Closed in this wave
- Revalidated canonical backend/frontend roots and active entrypoints.
- Reconfirmed `frontend/package.json` as the only active frontend manifest.
- Added explicit `header_details` support to the branding profile so organization requisites can be managed separately for header and footer layouts.
- Fixed branch/site branding resolution so overridden `branch_label` is carried into previewed and generated headers.
- Strengthened branding reproducibility with hashes for branding payload, header context, rendered sections, and preset content.
- Persisted branded preview/history inside the document wizard store, so operators do not lose preview context while moving through steps.
- Added server-side branded generation history via `/api/v1/branding/history`, backed by `PipelineRun.result_metadata.branding`.
- Added a reproducible repository audit script that writes `docs/audit/REPOSITORY_AUDIT.md`.
- Expanded the audit output so it enumerates canonical backend/frontend entrypoints, config inventory, required docs, root expectations, and compatibility-path guidance.
- Added a machine-readable repository audit snapshot at `docs/audit/REPOSITORY_AUDIT.json` for CI, tooling, and future waves.
- Added canonical `docs/WORKFLOWS_AND_EVENTS.md` and `docs/OBSERVABILITY.md` references for future implementation waves.
- Reduced frontend production bundle risk by splitting major vendor groups into predictable manual chunks.
- Added a dedicated `scripts/branded_document_smoke.py` smoke command and `make branded-smoke` entrypoint for fast verification of the canonical letterhead pipeline.
- Refreshed canonical repository docs to describe the real active paths and branded document flow.

## Remaining gaps
- Not every generation route automatically chains `generate -> apply_headers -> pdf`; some flows still require explicit `apply_headers` invocation or pipeline-profile configuration.
- Branding asset management still uses file IDs rather than a dedicated upload/media picker workflow on the branding screen.
- Preview history is persisted in frontend state, but not yet materialized as a server-side generation/audit projection.
- Duplicate legacy path pairs still remain on disk (`docs/ADR` vs `docs/adr`, `modules/approval` vs `modules/approvals`) and are documented rather than physically merged in this wave to avoid risky breakage.

## Additional gaps review — 2026-03-21
### Closed
- Fat-router notification logic was moved into a dedicated application module with reusable schemas/service boundaries.
- Invalid notification enum filters no longer rely on raw enum casting behavior.
- Training/LMS and risk-engine documentation now clearly state their true maturity and canonical code paths.

### Remaining
- Notification preferences exist, but escalation policies and richer delivery providers are still foundation-level rather than fully orchestrated.
- Calendar aggregation is centralized, but not every deadline-bearing module is yet projected into the common feed.
