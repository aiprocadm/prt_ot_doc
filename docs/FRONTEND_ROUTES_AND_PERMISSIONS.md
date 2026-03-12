# FRONTEND_ROUTES_AND_PERMISSIONS

## Purpose

This file is the operational reference for frontend route guards and permission mapping.

## Permission catalog

The frontend permission source is defined in src/permissions/permissions.ts.

| Permission | Meaning |
| --- | --- |
| dashboard.view | View dashboards |
| generation.view | Access generation flow |
| company.view | View companies |
| person.view | View people |
| template.view | View templates |
| template.create | Create templates |
| template.edit | Edit templates |
| template.delete | Delete templates |
| template.activate | Activate template version |
| pack.view | View packs |
| doc.view | View documents |
| doc.create | Create documents |
| doc.sign | Sign documents |
| doc.export | Export documents |
| file.view | View files/archive/search |
| task.view | View tasks/notifications/calendar |
| jobs.view | View jobs |
| risk.view | View risk data |
| risk.assess | Assess risk |
| risk.edit | Edit risk entries |
| risk.export | Export risk data |
| activity.view | View activities/CAPA |
| ppe.view | View PPE module |
| warehouse.view | View warehouse module |
| ppe.issue | Issue PPE |
| training.view | View training module |
| training.assign | Assign training |
| training.complete | Mark training complete |
| medical.view | View medical module |
| incident.view | View incidents |
| inspection.view | View inspections |
| audit_prep.view | View inspection/audit prep |
| fire_safety.view | View fire safety objects |
| fire_training.view | View fire training |
| fire_inspections.view | View fire inspections |
| reference.view | View references/checklists |
| contractor.view | View contractors |
| crm_finance.view | View CRM/finance module |
| integrations.view | View integrations module |
| client_portal.view | View client portal |
| admin.manage_roles | Manage admin role/tenant settings |
| admin.manage_tenants | Tenant administration capability |
| npa.view | View NPA module |
| audit.view | View audits |
| settings.view | View settings |
| reports.view | View reports/analytics/exports |

## Route guard matrix

All routes in this table were verified as existing and guarded in `AppRouter.tsx` as of Cycle 2.

Public/auth:

| Route | Permission | Guard |
| --- | --- | --- |
| /auth/login | none | Auth layout |

Core protected shell:

| Route | Permission | Guard |
| --- | --- | --- |
| / | authenticated | ProtectedRoute |
| /no-access | authenticated | ProtectedRoute |

Dashboards:

| Route | Permission | Guard |
| --- | --- | --- |
| /dashboard | dashboard.view | ProtectedRoute(permission) |
| /dashboard/executive | dashboard.view | ProtectedRoute(permission) |
| /dashboard/safety | dashboard.view | ProtectedRoute(permission) |
| /dashboard/training | dashboard.view | ProtectedRoute(permission) |
| /dashboard/ppe | dashboard.view | ProtectedRoute(permission) |
| /dashboard/client-delivery | dashboard.view | ProtectedRoute(permission) |

Master data and document flow:

| Route | Permission | Guard |
| --- | --- | --- |
| /companies | company.view | ProtectedRoute(permission) |
| /persons | person.view | ProtectedRoute(permission) |
| /templates | template.view | ProtectedRoute(permission) |
| /packs | pack.view | ProtectedRoute(permission) |
| /documents | doc.view | ProtectedRoute(permission) |
| /documents/wizard | doc.view | ProtectedRoute(permission) |
| /generation | generation.view | ProtectedRoute(permission) |

Approvals and EDO:

| Route | Permission | Guard |
| --- | --- | --- |
| /approvals/inbox | doc.view | ProtectedRoute(permission) |
| /approvals/outbox | doc.view | ProtectedRoute(permission) |
| /approval-routes | doc.view | ProtectedRoute(permission) |
| /signatures | doc.view | ProtectedRoute(permission) |
| /edo | doc.view | ProtectedRoute(permission) |

Files/search/archive:

| Route | Permission | Guard |
| --- | --- | --- |
| /files | file.view | ProtectedRoute(permission) |
| /archive | file.view | ProtectedRoute(permission) |
| /search | file.view | ProtectedRoute(permission) |

Tasks and scheduling:

| Route | Permission | Guard |
| --- | --- | --- |
| /tasks | task.view | ProtectedRoute(permission) |
| /notifications | task.view | ProtectedRoute(permission) |
| /calendar | task.view | ProtectedRoute(permission) |

OT/PB operational modules:

| Route | Permission | Guard |
| --- | --- | --- |
| /risk | risk.view | ProtectedRoute(permission) |
| /activities | activity.view | ProtectedRoute(permission) |
| /ppe | ppe.view | ProtectedRoute(permission) |
| /warehouse | warehouse.view | ProtectedRoute(permission) |
| /training | training.view | ProtectedRoute(permission) |
| /medical | medical.view | ProtectedRoute(permission) |
| /incidents | incident.view | ProtectedRoute(permission) |
| /inspections | inspection.view | ProtectedRoute(permission) |
| /inspection-plans | inspection.view | ProtectedRoute(permission) |
| /inspection-checklists | inspection.view | ProtectedRoute(permission) |
| /findings | inspection.view | ProtectedRoute(permission) |
| /prescriptions | inspection.view | ProtectedRoute(permission) |
| /corrective-actions | inspection.view | ProtectedRoute(permission) |
| /inspection-prep/packages | inspection.view | ProtectedRoute(permission) |
| /audit-prep | audit_prep.view | ProtectedRoute(permission) |

Fire safety:

| Route | Permission | Guard |
| --- | --- | --- |
| /fire-safety | fire_safety.view | ProtectedRoute(permission) |
| /fire-training | fire_training.view | ProtectedRoute(permission) |
| /fire-inspections | fire_inspections.view | ProtectedRoute(permission) |

References and contractors:

| Route | Permission | Guard |
| --- | --- | --- |
| /reference | reference.view | ProtectedRoute(permission) |
| /contractors | contractor.view | ProtectedRoute(permission) |

Admin:

| Route | Permission | Guard |
| --- | --- | --- |
| /admin | admin.manage_roles | ProtectedRoute(permission) |
| /admin/outbox | admin.manage_roles | ProtectedRoute(permission) |
| /admin/billing | admin.manage_roles | ProtectedRoute(permission) |
| /admin/layout-presets | admin.manage_roles | ProtectedRoute(permission) |

Compliance/settings/reports:

| Route | Permission | Guard |
| --- | --- | --- |
| /npa | npa.view | ProtectedRoute(permission) |
| /audit | audit.view | ProtectedRoute(permission) |
| /settings | settings.view | ProtectedRoute(permission) |
| /reports | reports.view | ProtectedRoute(permission) |
| /exports | reports.view | ProtectedRoute(permission) |
| /analytics/trends | reports.view | ProtectedRoute(permission) |
| /portal-requests | reports.view | ProtectedRoute(permission) |

Client portal:

| Route | Permission | Guard |
| --- | --- | --- |
| /client-portal/dashboard | client_portal.view | ProtectedRoute(permission) |
| /client-portal/packages | client_portal.view | ProtectedRoute(permission) |
| /client-portal/documents | client_portal.view | ProtectedRoute(permission) |
| /client-portal/history | client_portal.view | ProtectedRoute(permission) |
| /client-portal/requests | client_portal.view | ProtectedRoute(permission) |

Business integrations:

| Route | Permission | Guard |
| --- | --- | --- |
| /crm-finance | crm_finance.view | ProtectedRoute(permission) |
| /integrations | integrations.view | ProtectedRoute(permission) |

Pipelines/jobs/package generation:

| Route | Permission | Guard |
| --- | --- | --- |
| /pipelines/profiles | doc.view | ProtectedRoute(permission) |
| /pipelines/runs | doc.view | ProtectedRoute(permission) |
| /pipelines/runs/:id | doc.view | ProtectedRoute(permission) |
| /jobs | doc.view | ProtectedRoute(permission) |
| /jobs/:id | doc.view | ProtectedRoute(permission) |
| /package-profiles | doc.view | ProtectedRoute(permission) |
| /package-presets | doc.view | ProtectedRoute(permission) |
| /generate-pack/:presetId | doc.view | ProtectedRoute(permission) |
| /pack-runs/:id | doc.view | ProtectedRoute(permission) |

Fallback:

| Route | Permission | Guard |
| --- | --- | --- |
| * -> /companies | none | Redirect |

## Role normalization and aliases

Ability layer supports aliases for compatibility across identity/provider sources.

- Role aliases include mappings such as tenant_owner -> owner, methodist -> methodist_lawyer, jurist -> lawyer, hse_head -> ot_pb_head, contractor_auditor -> contractor_inspector.
- Permission aliases include mappings such as documents.read -> doc.view, documents.write -> doc.create, billing.read -> crm_finance.view, integrations.read -> integrations.view.

## Navigation coverage (Cycle 2 update)

SideNav now renders all major route groups with correct permission guards:

| Section | Nav items (Cycle 2) |
| --- | --- |
| Документооборот | Документы, Шаблоны, Пакеты, Поиск, Архив, Генерация |
| ЭДО / Согласования | Входящие задачи, Исходящие, Маршруты, Подписи, ЭДО |
| ОТ и ПромБез | Риски, Мероприятия, СИЗ, Склад, Обучение, Медосмотры, Инциденты, Проверки |
| Пожарная безопасность | Объекты ПО, Обучение ПБ, Проверки ПБ |
| Бизнес и аналитика | Компании, Сотрудники, Задачи, Отчёты, КРМ/Финансы, НПА *(new)*, Пакеты *(new)* |
| Интеграции | Интеграции, Подрядчики, Клиентский портал |
| Администрирование | Администрирование, Журнал аудита *(new)*, Справочники *(new)*, Настройки *(new)* |

## Scope-aware checks

In addition to permission checks, scope constraints can be applied on resources:

- tenant_id
- company_id
- site_id
- project_id
- contractor_id

ABAC rules are also applied for selected actions (for example document signing/export and risk/template state conditions).

## Delta: newly normalized routes (this task)

| Route | Permission | Notes |
|---|---|---|
| `/generation` | `doc.view` | Alias to document generation wizard flow. |
| `/archive` | `file.view` | Archive search entrypoint; `/archive/search` kept for compatibility. |
| `/warehouse` | `warehouse.view` | PPE warehouse registry (stock, batches, certificates). |
| `/crm-finance` | `crm_finance.view` | CRM/finance operational registry. |
| `/integrations` | `integrations.view` | Integration connectivity/status registry. |
| `/client-portal/*` | `client_portal.view` | Client portal routes moved under dedicated guard. |

## Update: Archive route behavior (this task)

| Route | Permission | Read-only behavior | Hidden actions |
|---|---|---|---|
| `/archive` and `/archive/search` | `file.view` | Available for read-only roles (auditor/client) as search + file-open context | No create/edit/delete mutations exposed; only view/download actions are rendered when file is present |

Additional notes:
- Archive filters are URL-param based and can be persisted as user saved views (local storage).
- Access denials continue to resolve through protected routes and the global access-denied flow.
