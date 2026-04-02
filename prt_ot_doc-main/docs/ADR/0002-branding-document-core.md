# ADR 0002: Branding profile as a first-class document-core input

## Decision
Persist company/site branding payloads and resolve an effective profile before header/footer rendering.

## Why
The previous layout preset flow stored only raw header/footer templates. Real issuance on a corporate letterhead needs a reusable and tenant-safe source of requisites, watermark preferences and preset selection.

## Consequences
- Branding is now an explicit backend/frontend API.
- Layout presets remain reusable and independent from a specific company.
- Generated previews expose reproducibility metadata for audit/debugging.
