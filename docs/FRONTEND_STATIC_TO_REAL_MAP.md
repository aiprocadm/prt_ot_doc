# Frontend Static -> Real Map

_Date:_ 2026-03-21

## Converted in this wave
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

## Still remaining
- Full PWA/offline UX remains not-realized.
- Some pages still aggregate from adjacent registries instead of having first-class backend projection endpoints.

## 2026-03-22 note
- No additional placeholder page was converted in this specific wave. The focus moved to backend document/pipeline hardening after the repo audit.
