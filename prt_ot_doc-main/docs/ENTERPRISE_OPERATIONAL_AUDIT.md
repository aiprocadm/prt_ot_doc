# Enterprise Operational Audit

**Дата:** 2026-03-24  
**Исполнитель роли:** Senior Full-Stack Engineer / Enterprise Platform Hardening Lead  
**Версия:** 1.0  
**Методология:** Фактический аудит кода — не предположение о соответствии ТЗ, а верификация состояния репозитория.

---

## 1. Обзор платформы

SaaS-платформа охраны труда, промышленной безопасности, пожарной безопасности, экологии, обучения, документооборота, ЭДО, рисков, СИЗ, проверок, инцидентов, CRM, billing, client portal, mobile/PWA.

**Общий объём:** ~62 000 строк Python (backend) + ~279 TypeScript/TSX файлов (frontend).

---

## 2. Backend: маршруты и сервисы

### 2.1 Operationally usable маршруты

| Маршрут | Tenant-scoped | AuthZ | Audit | Структурные ошибки | Статус |
|---------|:---:|:---:|:---:|:---:|--------|
| `auth.py` | ✅ | ✅ (9 checks) | — | Нормализованы | **USABLE** |
| `dashboard.py` | ✅ | ✅ (abac) | — | Нормализованы | **USABLE** |
| `workspace.py` | ✅ | ✅ (rbac) | — | Нормализованы | **USABLE** |
| `briefings.py` | ✅ | ✅ | ✅ (bulk audit) | Нормализованы | **USABLE** |
| `documents.py` | ✅ | ✅ (abac) | ✅ | Нормализованы | **USABLE** |
| `incidents.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `inspections.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `training.py` / `training_next.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `ppe.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `persons.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `companies.py` | ✅ | ✅ (abac) | ✅ | Нормализованы | **USABLE** |
| `sites.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `packs.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `tasks.py` | ✅ | ✅ (abac) | ✅ | Нормализованы | **USABLE** |
| `npa.py` | ✅ | ✅ (abac) | ✅ | Нормализованы | **USABLE** |
| `risk.py` / `risk_enterprise.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `medical.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `safety_ops.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `pwa_sync.py` (bootstrap v4) | ✅ | ✅ (rbac) | ✅ | Нормализованы | **USABLE** |
| `health.py` | — | — | — | Нормализованы | **USABLE** |
| `audit.py` | ✅ | ✅ | — | Нормализованы | **USABLE** |
| `billing.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `webhooks.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `outbox_admin.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `integration_readiness.py` | ✅ | ✅ | — | Нормализованы | **USABLE** |
| `replace.py` | ✅ | ✅ (abac, admin/employee) | ✅ | Нормализованы | **USABLE** |
| `external_registry.py` | ✅ | ✅ (rbac, admin/owner/integrations) | ✅ | Базовые ответы, требует дальнейшей error normalization | **USABLE** |
| `public_api.py` | ✅ | ✅ (machine-key auth + scope checks) | ✅ для admin router | Scope-aware | **USABLE (machine API)** |
| `client_portal.py` | ✅ (portal token auth) | ✅ (token-based, не RBAC) | ✅ | Нормализованы | **USABLE (специфичный auth)** |
| `notifications.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `prescriptions.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `contracts.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `invoices.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |
| `attestations.py` | ✅ | ✅ | ✅ | Нормализованы | **USABLE** |

### 2.2 Partially usable / Foundation маршруты

| Маршрут | Проблема | Статус |
|---------|----------|--------|
| `calendar.py` | Минимальный authz (rbac 2 вхождения), нет audit на write | **FOUNDATION** |
| `journals.py` | Слабый authz coverage | **FOUNDATION** |
| `obligations.py` | rbac 2 вхождения | **FOUNDATION** |
| `orders.py` | rbac 3 вхождения | **FOUNDATION** |
| `items.py` | Пустой router без активных endpoints. Не operational gap, но требует cleanup/documentation. | **LOW-DEBT** |

### 2.3 Confirmed stubs / deferred / non-production

#### `backend/app/api/routes/ws_stub.py`
```
transport_mode = "polling_fallback"
provider_mode = "non_production"
websocket_available = False
reason = "websocket_transport_pending"
```
**Факт:** WebSocket transport не реализован. Роут предоставляет polling fallback из outbox projections. Tenant-scoped. Задокументирован как non-production.

#### `backend/app/celery/tasks/document_jobs_required.py`
```
bridge_mode = "internal-fallback"
provider_mode = "non_production"
```
**Факт:** Compatibility execution bridge. Реальные внешние адаптеры для `export_report` и `sync_integration` отсутствуют. Работает internal orchestration (не mock — реальная internal логика), но без реального провайдера.

#### `backend/app/services/pipeline_step_handlers.py`
**Факт:** Реализованы:
- `artifact_step_handler` — создаёт реальные file records через FileService
- `signature_step_handler` — internal deterministic-snapshot (не внешний crypto-провайдер)
- `edo_step_handler` — вызывает `get_edo_integration()`, которая в non-production mode возвращает stub

**Deferred stages:** EDO step использует stub provider. Все остальные шаги — internal real implementations.

#### `backend/app/services/integrations/stubs.py`
**Факт:** Stub-провайдеры для:
- `StubAccountingIntegration` (1C) — возвращает `provider_mode: non_production`
- `StubEDOIntegration` — заглушка ЭДО
- `StubEISOTIntegration` — заглушка EISOT (обучение)
- `StubFRDOIntegration` — заглушка ФРДО
- `DisabledAccountingIntegration` — выбрасывает `IntegrationDisabledError`

**Изоляция:** Чистая, через `factory.py`. `provider_registry.py` детектирует non-production по имени провайдера.

#### `backend/app/api/routes/approval_signing_v1.py`
**Факт:** Строка 335: `if payload.provider in {"stub", "internal-fallback"}:` — явный внутренний fallback путь для signing. Нет внешнего crypto-провайдера (КриптоПро, etc.).

#### `backend/app/api/routes/approval_orchestration.py`
**Факт:** `provider_code: str = "internal-fallback"` (строки 120, 128). Internal orchestration реальная, но provider_code явно показывает internal-fallback режим. Нет внешнего оператора.

#### `backend/app/api/routes/edo_workflow.py`
**Факт:** Импортирует `edo_status_simulation_job` из `app.tasks`. Simulation job — deferred/mock семантика для ЭДО статусов. Реальный ЭДО-оператор не подключён.

---

## 3. Backend: сервисы

### 3.1 Fat files (архитектурный долг)

| Файл | Строк | Проблема |
|------|------:|---------|
| `app/models/models.py` | 2784 | Монолитный файл моделей. Частично разбит (есть отдельные models/), но основная масса не декомпозирована |
| `app/tasks.py` | 1720 | Смесь Celery tasks разных доменов |
| `app/api/routes/risk.py` | 1418 | Fat route file |
| `app/api/v1/router.py` | 1394 | Гигантский router-регистратор |
| `app/services/pipeline.py` | 1070 | Fat service |
| `app/services/pipelines_orchestrator.py` | 808 | Крупный orchestrator |
| `app/api/routes/packs.py` | 1095 | Fat route |
| `app/api/routes/edo_workflow.py` | 695 | Large route |
| `app/api/routes/approval_signing_v1.py` | 607 | Large route |

### 3.2 Duplicate / Parallel module boundaries

**Подтверждённые коллизии:**
- `app/core/tenancy.py` + `app/core/tenant.py` + `app/tenancy/` — три точки tenant context (частично объединены, но граница размыта)
- `app/core/security.py` + `app/core/security/` — flat module и директория с одним именем
- `app/domains/` + `app/modules/` — два слоя доменной логики с разным охватом (modules шире, domains старее)
- `app/tasks.py` + `app/celery/tasks/` — celery tasks в двух местах

### 3.3 Tenant context в background jobs

**Статус:** `tenant_context` и `ensure_tenant_schema` используются в `document_jobs_required.py`. Correlation ID propagation через `task_context.py`. Принципиально реализовано.

---

## 4. Frontend: страницы

### 4.1 Operationally usable страницы

| Страница | EmptyState | Loading | Error | Permission | Статус |
|----------|:---:|:---:|:---:|:---:|--------|
| `DashboardPage.tsx` | ✅ | ✅ | ✅ | ✅ (AttentionPanel + workspace API + top CTA gates aligned to `doc.create`) | **USABLE** |
| `FireSafetyPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `MedicalPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `ContractorsPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `AdminPage.tsx` | ✅ | ✅ | ✅ | ✅ (ADMIN_MANAGE_ROLES check) | **USABLE** |
| `SettingsPage.tsx` | — | ✅ | ✅ | — | **USABLE (basic)** |
| `IncidentsPage.tsx` | ✅ | ✅ | ✅ | ✅ (`Can` + `incident.create` / `incidents.write` alias) | **USABLE** |
| `InspectionsPage.tsx` | ✅ | ✅ | ✅ | ✅ (`Can` + `inspection.create` / `inspections.write` alias) | **USABLE** |
| `PersonsPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |
| `TasksPage.tsx` | ✅ | ✅ | ✅ | ✅ (`TaskTable` close action + focused-task close CTA на `task.update` / `tasks.write`) | **USABLE** |
| `TrainingPage.tsx` | ✅ | ✅ | ✅ | ✅ (teacher surface и teacher API только при `training.assign` + page-level assign CTA с fallback) | **USABLE** |
| `DocumentsPage.tsx` | ✅ | ✅ | ✅ | ✅ (Can component) | **USABLE** |
| `ApprovalsInboxPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |
| `ApprovalsOutboxPage.tsx` | ✅ | ✅ | ✅ | ✅ (`/admin/outbox*` RBAC admin) | **USABLE** |
| `CompaniesPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |
| `FilesPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |
| `PacksPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |
| `PackagePresetsPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `PackageProfilesPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `PpePage.tsx` | ✅ | ✅ | ✅ | ✅ (`Can` + `ppe.issue` для quick issue CTA) | **USABLE** |
| `CalendarPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |
| `WorkflowPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `SafetyDashboardPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `TrainingDashboardPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `ClientDeliveryDashboardPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `PortalRequestsPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `FireInspectionsPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `FireTrainingPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `InspectionChecklistsPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `InspectionPlansPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `InspectionPrepPackagesPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `ActivitiesPage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `ReferencePage.tsx` | ✅ | ✅ | ✅ | — | **USABLE (basic)** |
| `BriefingsPage.tsx` | ✅ | ✅ | ✅ | ✅ (write-actions gated by `training.assign`: remind/create/assign/sign/complete) | **USABLE** |
| `ReportsPage.tsx` | ✅ | ✅ | ✅ | ✅ (export CTA gated by `doc.export`/`reports.view`) | **USABLE** |
| `ClientPortal*Pages.tsx` | ✅ | ✅ | ✅ | — | **USABLE** |

### 4.2 Foundation/projection страницы (экраны есть, но operationally незрелые)

| Страница | Что не хватает |
|----------|---------------|
| `RiskPage.tsx` | Нет EmptyState, нет loading/error states |
| `EdoPage.tsx` | Нет EmptyState/loading/error |
| `SignaturesPage.tsx` | Нет EmptyState/loading/error |
| `TemplatesPage.tsx` | Нет EmptyState/loading/error |
| `AnalyticsTrendsPage.tsx` | Нет loading/error states |
| `NpaPage.tsx` | Нет EmptyState/loading/error |

### 4.3 Permission awareness

**Критическая находка:** permission-aware компоненты (`Can`, `PermissionGate`, `ActionButton`, `usePermission`) всё ещё применены точечно, а не системно. Подтверждённые примеры:
- `DocumentsPage.tsx`
- `IncidentsPage.tsx`
- `InspectionsPage.tsx`
- `TaskTable.tsx`
- `TrainingPage.tsx`
- `PpePage.tsx`
- `DashboardPage.tsx`
- `ReportsPage.tsx`
- `BriefingsPage.tsx`
- `PipelineRuns.tsx`, `PipelineRunDetails.tsx`, `PipelineBuilderPage.tsx`

**Часть operational страниц** по-прежнему не используют action-level permission awareness системно. Кнопки "Создать", "Удалить", "Экспортировать" всё ещё встречаются без role-based filtering вне приоритетно закрытых экранов.

### 4.4 Unsaved changes protection

**Факт:** Ни одна страница не реализует `beforeunload`/`useFormDirty`/`unsaved changes prompt`. Критические формы (документы, шаблоны, wizards) не защищены от случайной потери данных.

### 4.5 Bulk actions

**Факт:** В backend только `briefings.py` имеет bulk-create endpoint. В frontend нет ни одного bulk selection UI. Массовые операции (закрытие задач, назначение обучения, выдача СИЗ) отсутствуют.

### 4.6 PWA / Offline

**Состояние:**
- `vite.config.ts` содержит `VitePWA` с `registerType: "autoUpdate"` ✅
- `/api/pwa/bootstrap` (v4) возвращает: current_user, route_permissions, dictionaries, offline_queue, sync_state, diagnostics ✅
- `ConnectivityBanner.tsx` — offline banner ✅
- `pwa/register.ts` — service worker registration с auto-update ✅
- **Нет:** conflict resolution UI, retry/resume UX, local draft persistence, sync diagnostics для пользователей
- **Нет:** dedicated offline queue manager компонента
- **Нет:** field scenario support (briefing mark, incident draft, checklist draft)

---

## 5. Role-based workspaces

### 5.1 Backend

**`/workspace/attention`** — реализован, tenant-aware, rbac-protected. Возвращает:
- overdue_tasks, due_soon_tasks, overdue_deadlines
- pending и failed sync batches
- readiness_blockers (overdue PPE, expired training, expired contracts, overdue incidents, overdue inspections)
- recommendations
- items с severity и deep links

**`/workspace/task-inbox`** — реализован, tenant-aware.

**Что не хватает:**
- Отдельные role-based projections (safety lead, HR, line manager, contractor)
- Timeline/event summaries
- Recent drafts projection
- Dependency map (NPA → template → package → approval route)

### 5.2 Frontend

**`DashboardPage.tsx`** использует workspace API:
- task inbox (overdue/active filter)
- attention blockers
- deep links на `taskInboxLink`, `entityContextPath`
- AttentionPanel компонент

**Что не хватает:**
- Role-specific dashboards (safety lead vs. HR vs. contractor)
- "Что я должен делать сейчас" как primary CTA
- Recent items/drafts секция
- Recommendations блок интегрирован слабо

---

## 6. Document Core

### 6.1 Lifecycle coverage

| Этап | Статус |
|------|--------|
| Template upload | ✅ USABLE |
| Template versioning | ✅ USABLE |
| Lint | ✅ USABLE |
| Preview | ✅ USABLE |
| Branding/header-footer | ✅ USABLE |
| Replace engine | ✅ USABLE |
| PDF conversion | ✅ USABLE (LibreOffice-based) |
| Document packs | ✅ USABLE |
| Approval orchestration | ✅ Internal-fallback (non-production provider) |
| Signing | ✅ Internal deterministic snapshot (не crypto-провайдер) |
| ЭДО workflow | ✅ Internal + simulation job (non-production) |
| Archive | Нет явного архивного маршрута |

### 6.2 Document Passport

`backend/app/core/utils/pdf_passport.py` существует. Степень completeness неизвестна без глубокого чтения.

### 6.3 Readiness Score

Backend `/workspace/attention` имеет `readiness_blockers`. Отдельного `document_readiness_score` endpoint нет.

---

## 7. Data Quality

**Факт:** Отдельного Data Quality модуля/сервиса нет. `models.py` не содержит `DataQualityIssue` модели. В workspace blockers реализована часть проверок:
- Overdue PPE issues
- Expired training
- Expired contracts
- Overdue incidents
- Overdue inspections

**Что отсутствует:**
- Персистирование DQ-issues
- Обнаружение дублей
- Employee readiness score
- Contractor readiness score
- Template/document completeness score
- DQ dashboard для admin

---

## 8. Admin / Governance / Diagnostics

### Backend admin API coverage

| Компонент | Статус |
|-----------|--------|
| `/integrations/readiness` | ✅ USABLE — provider health checks |
| `/admin/users` | ✅ USABLE |
| `/admin/authz` | ✅ USABLE |
| `/webhooks` | ✅ USABLE — retry telemetry |
| `/outbox-admin` | ✅ USABLE |
| `/audit` | ✅ USABLE |
| `/billing` | ✅ USABLE |
| Tenant health endpoint | ❌ MISSING |
| Job/queue diagnostics | Partial (jobs.py) |
| Feature/module enablement | ❌ MISSING |
| Startup readiness / onboarding | ❌ MISSING |

### Frontend AdminPage

`AdminPage.tsx` (128 строк) — уже operational console с:
- tenant health snapshot
- outbox status
- webhook status
- API tokens count
- audit items
- integration readiness
- attention summary

**Что не хватает:** queue/job diagnostics, feature flags visibility, startup readiness, data quality overview, billing/usage trends.

---

## 9. Reliability / Observability

| Компонент | Статус |
|-----------|--------|
| Health + readiness endpoint | ✅ Postgres, Redis, MinIO, ClamAV, LibreOffice |
| POISONED status в job_engine | ✅ |
| Webhook retry + DLQ | ✅ webhook_retry_telemetry.py |
| Correlation ID / Trace ID | ✅ propagated |
| Celery + background jobs | ✅ |
| Heartbeat/watchdog | ❌ MISSING |
| Failed job cleanup/integrity | Partial |
| Structured logs | ✅ logging_config.py |
| Metrics | ✅ core/metrics.py |
| Runbooks | docs/ содержит часть, нет единого runbook |

---

## 10. Tests coverage

Тестов достаточно много (~85 файлов). Покрытие:
- access parity (tenant isolation): ✅ многие модули
- error contracts: ✅ многие модули
- billing enforcement: ✅
- pwa sync: ✅
- workspace projections: ✅
- pipeline orchestrator: ✅
- approval/sign/edo: ✅
- briefings service: ✅

**Что не покрыто тестами:**
- Data quality checks (модуль отсутствует)
- Bulk operations (endpoints отсутствуют)
- Unsaved changes (frontend)
- Conflict resolution offline (frontend)
- Unsaved changes protection (frontend)
- Role-specific workspace projections
- Role-specific workspace projections

---

## 11. Сводная матрица зрелости

| Область | Зрелость | Приоритет |
|---------|----------|-----------|
| Core document lifecycle | 🟡 75% — signing и ЭДО non-production | HIGH |
| Tenant isolation | 🟢 85% — несколько роутов без RBAC | HIGH |
| AuthZ consistency | 🟡 68% — backend критические gaps закрыты, frontend action-level permissions всё ещё массово отсутствуют | CRITICAL |
| Role workspaces / attention | 🟡 70% — backend есть, frontend базовый | HIGH |
| Data quality | 🔴 20% — практически отсутствует | HIGH |
| PWA / offline | 🟡 50% — foundation есть, field scenarios нет | MEDIUM |
| Admin diagnostics | 🟡 65% — частичное покрытие | MEDIUM |
| Bulk actions | 🔴 10% — почти нет | MEDIUM |
| Reliability / observability | 🟡 70% — основа есть | MEDIUM |
| Empty states / UX maturity | 🔴 40% — половина страниц без states | HIGH |
| Unsaved changes protection | 🔴 0% — не реализовано | HIGH |
| Test coverage | 🟡 65% — хорошее по контрактам, слабое по DQ/bulk | MEDIUM |

---

## 12. Подтверждённые факты (из ТЗ)

- ✅ `backend/app/api/routes/ws_stub.py` = deferred websocket (polling fallback, non_production, tenant-scoped)
- ✅ `backend/app/celery/tasks/document_jobs_required.py` = deferred semantics (internal-fallback, non_production)
- ✅ `backend/app/services/pipeline_step_handlers.py` = deferred EDO stage (stub provider), остальные шаги — internal real
- ✅ `backend/app/services/integrations/stubs.py` = stub providers (1C, EDO, EISOT, FRDO), чисто изолированы через factory
- ✅ `backend/app/api/routes/approval_signing_v1.py` = stub/internal-fallback provider path (строка 335)
- ✅ `backend/app/api/routes/approval_orchestration.py` = mock provider path (internal-fallback, строки 120/128)
- ✅ `backend/app/api/routes/edo_workflow.py` = mock/stub semantics (использует `edo_status_simulation_job`)
- ✅ `frontend/vite.config.ts` содержит `VitePWA` plugin
- ✅ `/api/pwa/bootstrap` (v4) возвращает: current_user, route_permissions, dictionaries, offline_queue, sync_state, diagnostics
- ✅ Многие страницы используют real snapshot APIs, но не имеют operational maturity

---

*Аудит проведён на основе фактического чтения кода. Дата: 2026-03-24.*
