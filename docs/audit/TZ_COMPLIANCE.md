# TZ Compliance Audit — Improvement Wave

## Scope
- Obligations engine: inspections + attestations.
- Pipeline: explicit QR-code + watermark stages.
- Incidents: prescriptions scaffolding linked to inspections.

## Summary of changes
- Added inspections and attestations coverage to obligations/tasks (scheduling, reminders, overdue).
- Added CRUD for attestations and prescriptions with audit logging.
- Added pipeline stages for QR-code and watermark (feature-flagged).
- Expanded tests for obligations, reminders, pipeline stages, and new entities.

## Remaining notes
- QR/watermark stages are placeholders and should be replaced with actual PDF stamping in P2.
- Reminder windows are tenant-configurable via `tenant.settings.obligations.reminder_days`.
