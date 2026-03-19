# Enterprise wave notes — 2026-03-19

## LMS
- `GET /api/v1/training/analytics/overview` aggregates progress/completion/retake/material-type metrics for the teacher/learner cabinets.
- `POST /api/v1/training/enrollments/{id}/retake` resets completion state into a controlled retake lifecycle without recreating the enrollment.

## BI / DWH exports
- `GET /api/v1/exports/datasets` exposes tenant-safe dataset contracts for BI/DWH consumers.
- `POST /api/v1/exports/schedules/{id}/run-now` provides a manual trigger foundation for scheduled analytics exports.

## Public / machine API
- `POST /api/v1/public/integrations/webhooks/subscriptions` allows machine clients with `integrations:write` scope to provision callback subscriptions in a tenant-safe way.
- Public list contracts continue to use stable `limit/offset/sort_by/sort_order` behavior.

## Government / enterprise integrations
- `GET /api/v1/integrations/readiness` summarizes configured providers, live health for enabled adapters, and contract-only readiness for EPGU/OIDC/LDAP.
- The integrations UI now surfaces provider readiness and webhook delivery pressure alongside the existing outbox/event pipeline tables.
