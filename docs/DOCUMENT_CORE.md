# DOCUMENT_CORE

## Canonical flow
`Template -> branding profile -> layout preset -> rendered preview -> apply headers -> PDF -> approval/sign/archive`

## Implemented building blocks
- Branding profile inheritance: tenant -> company -> site.
- Letterhead sections: first / odd / even headers and footers.
- Watermark resolution: preset + branding profile + request override.
- Reproducibility metadata: tenant/company/site/preset/version timestamps.
- Wizard integration: branded preview and generation payload enrichment on step 5.

## Operational note
Preview and generation-context preparation are production-ready. Full automatic invocation of `apply_headers` inside every generation pipeline is still partially explicit: currently header application remains a dedicated API/job step after DOCX generation unless a pipeline profile orchestrates it.
