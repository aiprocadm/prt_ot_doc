# Frontend Static -> Real Map

_Date:_ 2026-03-22

## Already moved from static/foundation to real data
- `ContractorsPage` -> `/companies`, `/sites`, `/contracts`.
- `ReferencePage` -> `/npa`, `/ppe/items`, `/training/programs`, `/templates`, `/briefings/templates`.
- `SettingsPage` -> `/tenancy/context`, `/notifications/settings/me`, `/api-tokens`.
- `ActivitiesPage` -> `/tasks`, `/corrective-actions`.
- `MedicalPage` -> `/medical/exams`, `/persons`, `/tasks?type=medical_requirement`.
- `FireSafetyPage` -> `/sites`, `/inspections`, `/tasks?type=inspection`.
- `FireTrainingPage` -> `/briefings/templates`, `/briefings/journals`, `/briefings/entries/overdue`, `/training/programs`.
- `FireInspectionsPage` -> `/inspections`, `/prescriptions`, `/tasks`.
- `InspectionChecklistsPage` -> projection over `/inspections` + `/prescriptions`.
- `InspectionPlansPage` -> `/inspections`.
- `InspectionPrepPackagesPage` -> projection over `/inspections`, `/prescriptions`, `/tasks`, `/templates`.
- `AdminPage` -> `/tenancy/context`, `/admin/outbox`, `/webhooks/endpoints`, `/api-tokens`, `/audit`.

## Strengthened in this wave
- Frontend shell now has a real PWA baseline: generated manifest, service worker, runtime registration, and cache strategy in the Vite build. This improves platform readiness but does not mean offline operations are fully complete yet.

## Remaining gaps
- Offline queue UI, sync status center, conflict resolution UI, and draft resume/retry flows are still incomplete.
- Some pages still compose operational snapshots from adjacent registries instead of dedicated backend projection endpoints.
