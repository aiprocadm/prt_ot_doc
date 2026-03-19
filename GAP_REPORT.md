# GAP REPORT

## Closed in this wave
- Reconfirmed canonical backend/frontend roots and active entrypoints.
- Kept `frontend/package.json` as the single active frontend manifest and documented it clearly.
- Fixed branding persistence mismatch for site-scope preferred presets.
- Added resolved watermark + stronger reproducibility metadata to branding preview.
- Upgraded branding UI from company-only editor to organization/branch-aware operator console.
- Upgraded layout preset editor from create-only stub to load/edit workflow.

## Remaining gaps
- No full browser-driven E2E for branded generation → PDF → sign → archive yet.
- Branding preview remains textual rather than pixel-perfect PDF canvas preview.
- Layout presets do not yet have version diffing/history UI.
- Documents wizard still relies on manual IDs in some steps and needs deeper integration with organizations/templates catalogs.
