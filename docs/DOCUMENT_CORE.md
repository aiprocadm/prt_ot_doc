# Document core

## Pipeline
1. Template selection/versioning.
2. Effective branding resolution (`tenant -> company -> site`).
3. Layout preset selection.
4. Header/footer rendering with placeholders.
5. DOCX header/footer injection.
6. Replace stage.
7. PDF conversion.
8. Approval / sign / archive.

## Production-minded capabilities
- Separate first/odd/even header/footer content.
- Stable DOCX relationship/content-type generation for inserted parts.
- Watermark resolution from preset + branding profile + optional preview override.
- Reproducibility passport returned by branding preview.
- Company and site scope branding inheritance.

## Fast issuance use case
1. Select company and optional site.
2. Pick or maintain a preferred preset.
3. Preview generated header/footer in `/documents/branding`.
4. Apply the same preset in the generation flow to avoid manual footer/header edits.
5. Continue downstream to PDF/sign/archive.
