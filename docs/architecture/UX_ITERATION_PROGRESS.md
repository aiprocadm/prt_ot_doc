# UX Iteration Progress (IA + P1/P2)

## What improved

- Added explicit entry point for create-document flow in `DocumentsPage` header (`Создать документ`).
- Added clear post-create feedback in `CompaniesPage` (toast + focused details intent).
- Synced filters with URL query in `TasksPage` (`type`, `overdue`, `priority`) to preserve context.
- Synced status filter with URL in `InspectionsPage` (`status`) and improved post-create focus via query params.
- Localized inspection type/status labels for user-facing UI text.
- Localized training material/status labels and replaced technical error placeholders with readable messages.
- Improved risk readability:
  - company name in table instead of raw `company_id`,
  - risk status labels (`Черновик` / `Утвержден`),
  - score level hints (`Низкий/Средний/Высокий/Критический`),
  - in-form per-hazard score hint from probability × severity.

## Why this matters

- Reduces context breaks during key scenarios (create company, assign task, run inspection, upload document).
- Makes navigation and filtering behavior predictable after reload/share/open from workspace links.
- Replaces backend/system codes with user language, improving first-run comprehension.

## Validation status

- Frontend lint: passing with `--max-warnings=0`.
- Added/updated UI tests for human-readable labels in training/inspections pages.

## Next recommended step

- Add targeted tests for post-create focus behavior (`task_id`/`entity_id` query sync) and a compact e2e assertion for key IA flows with configured test credentials.
