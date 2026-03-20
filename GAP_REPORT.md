# GAP_REPORT

## Closed in this wave
- Reconfirmed canonical frontend/backend roots and active entrypoints.
- Reconfirmed `frontend/package.json` placement.
- Strengthened branding preview contract with `apply_headers_payload`, `wizard_defaults`, preset-source metadata and inheritance resolution chain.
- Wired document wizard step 5 to real branding APIs with organization/site/preset selection, multi-section letterhead preview and reproducibility preview.

## Remaining gaps
- Not every generation path automatically triggers `apply_headers`; some flows still require explicit post-generation job invocation.
- Branding asset upload UX still relies on file IDs rather than a dedicated media picker on the branding page.
- Preview history in the wizard is UI-local rather than persisted server-side generation history.
