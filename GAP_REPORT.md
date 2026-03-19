# GAP REPORT

## Closed in this wave
- Canonical frontend root/package.json reaffirmed and documented.
- Backend/frontend entrypoints re-documented from actual code.
- Added explicit branding profile API and UI.
- Strengthened header/footer engine to generate section references and distinct first/odd/even parts.
- Fixed frontend company update method to match backend PATCH contract.

## Remaining gaps
- Full end-to-end DOCX -> PDF -> sign -> archive browser-driven scenario is still covered mainly by API/smoke tests, not dedicated UI e2e.
- Branch-level branding UI is currently company-first; site overrides are API-ready but not yet exposed with a dedicated selector/editor.
- Layout preset management UI remains minimal and should evolve into a richer catalog with diff/version preview.
