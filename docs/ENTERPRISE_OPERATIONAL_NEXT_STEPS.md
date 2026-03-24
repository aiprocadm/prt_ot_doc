# Enterprise Operational Next Steps

**Дата:** 2026-03-24  
**Версия:** 1.0  
**Основа:** `ENTERPRISE_OPERATIONAL_REMAINING_GAPS.md` + `ENTERPRISE_OPERATIONAL_PLAN.md`

---

## Немедленные действия (Волна A — до следующей демонстрации)

Это минимальный набор исправлений для перевода платформы из "foundation-level" в "can demonstrate to enterprise customer".

---

### A1. ЗАВЕРШЕНО — Добавить RBAC в `replace.py`

**Файл:** `backend/app/api/routes/replace.py`  
**Gap:** SEC-001  
**Что сделано:**

```python
_REPLACE_READ_ROLES = ["admin", "employee"]
_REPLACE_WRITE_ROLES = ["admin", "employee"]

ReaderAccess = Annotated[
  AccessContext,
  Depends(abac(_tenant_resource_id, required_roles=_REPLACE_READ_ROLES, action="read replace reports")),
]
EditorAccess = Annotated[
  AccessContext,
  Depends(abac(_tenant_resource_id, required_roles=_REPLACE_WRITE_ROLES, action="manage document replace")),
]
```

**Проверка:** Добавлен regression test на паритет ролей в `backend/tests/test_replace_error_contract.py`.

---

### A2. ЗАВЕРШЕНО — Добавить RBAC в `external_registry.py`

**Файл:** `backend/app/api/routes/external_registry.py`  
**Gap:** SEC-002  
**Что сделано:** Добавлен `rbac(["admin", "owner", "integrations"])` для jobs и webhook endpoints. Добавлен regression test `backend/tests/test_external_registry_access_parity.py`.

---

### A3. ЧАСТИЧНО ЗАВЕРШЕНО — Реализовать `useUnsavedChanges` hook

**Файл новый:** `frontend/src/hooks/useUnsavedChanges.ts`  
**Gap:** UX-002  
**Что сделано:**

```typescript
import { useEffect } from "react";

/**
 * Prevents accidental navigation when form has unsaved changes.
 * Shows browser native dialog on tab close / browser navigation.
 * For in-app navigation use isDirty + React Router prompt.
 */
export function useUnsavedChanges(isDirty: boolean, message = "Есть несохранённые изменения. Покинуть страницу?"): void {
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = message;
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty, message]);
}
```

**Уже применено к:**
- `DocumentsWizardPage.tsx` — отслеживать `isDirty` из react-hook-form
- `GeneratePackWizardPage.tsx`
- `BrandingSettingsPage.tsx`

**Что осталось:** распространить hook на остальные критичные формы, где состояние ещё не persist-ится автоматически.

**Тест:** `frontend/src/__tests__/useUnsavedChanges.test.tsx`

---

### A4. ВЫСОКИЙ — Loading/Error/Empty states для 8 приоритетных страниц

**Gap:** UX-003  
**Шаблон применения:**

```tsx
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { useAsyncResource } from "@/hooks/useAsyncResource";

// В компоненте:
const { data, loading, error, reload } = useAsyncResource({
  loader: useCallback(() => someApi.getSnapshot(), []),
  initialData: { items: [] },
  errorMessage: "Не удалось загрузить данные"
});

// В JSX:
<ErrorState error={error ?? undefined} onRetry={() => void reload()} />
{loading ? <LoadingScreen label="Загрузка..." /> : null}
{!loading && !error && data.items.length === 0 ? (
  <EmptyState title="Записей не найдено" description="Добавьте первую запись." />
) : null}
```

**Очерёдность:**
1. `RiskPage.tsx` — критично для ежедневного использования safety teams
2. `TemplatesPage.tsx` — критично для document core
3. `NpaPage.tsx`
4. `EdoPage.tsx` — + добавить provider mode warning
5. `SignaturesPage.tsx` — + добавить provider mode warning

---

## Волна B — Корпоративное удобство (1-2 спринта)

### B1. Provider Status Endpoint

**Gap:** OPS-005  
**Файл новый:** добавить в `backend/app/api/routes/integration_readiness.py` или как отдельный `admin_providers.py`

```python
@router.get("/admin/provider-status")
async def get_provider_status(
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = Depends(rbac()),
) -> ProviderStatusResponse:
    ...
```

**Response:**
```json
{
  "generated_at": "...",
  "production_ready": false,
  "providers": {
    "signing": {"mode": "non_production", "adapter": "internal-fallback", "warning": "..."},
    "edo": {"mode": "non_production", "adapter": "stub-edo"},
    "accounting": {"mode": "non_production", "adapter": "stub-1c"},
    "websocket": {"mode": "non_production", "adapter": "polling_fallback"},
    "frdo": {"mode": "non_production", "adapter": "stub-frdo"},
    "eisot": {"mode": "non_production", "adapter": "stub-eisot"}
  },
  "blocking_for_golive": ["signing", "edo"]
}
```

**Frontend:** Добавить `ProviderStatusWidget` в `AdminPage.tsx`.

---

### B2. Tenant Health Score Endpoint

**Gap:** OPS-004  
**Файл:** `backend/app/api/routes/admin_authz.py` или новый `admin_health.py`

```python
@router.get("/admin/tenant-health")
async def get_tenant_health(...) -> TenantHealthResponse:
    # aggregate: failed jobs, outbox pending, workspace blockers, DQ issues (когда появятся)
```

**Frontend:** Health score gauge в `AdminPage.tsx`.

---

### B3. Role-specific Workspace Projections

**Gap:** OPS-002  
**Файл:** `backend/app/api/routes/workspace.py`

Добавить:
```python
@router.get("/role-summary")
async def role_workspace_summary(
    role: str = Query(default=None),
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
) -> RoleWorkspaceSummary:
    ...
```

Роли: `safety_lead`, `hr`, `line_manager`, `contractor_manager`, `executive`.

**Frontend:** В `DashboardPage.tsx` — conditional rendering на основе `current_user.role`.

---

### B4. Unified Task Projection — расширение источников

**Gap:** OPS-003  
**Файл:** `backend/app/api/routes/workspace.py`

В `workspace_task_inbox` добавить источники:
- `TrainingEnrollment` с `due_at < now` и статусом не completed
- `PPEIssue` с `status=overdue`
- `MedicalExam` с `valid_until < now`
- `Incident` без assigned/closed старше N дней

---

### B5. Action-level Permission Gates (Приоритетные страницы)

**Gap:** UX-001  
**Статус:** ЧАСТИЧНО ЗАВЕРШЕНО — `IncidentsPage.tsx` и `InspectionsPage.tsx` уже переведены на permission-aware create CTA с явными `incident.create` / `inspection.create` permission keys и backend alias mapping для `incidents.write` / `inspections.write`; `PpePage.tsx` gates quick issue CTA by `ppe.issue`; `TrainingPage.tsx` больше не показывает teacher surface и не вызывает teacher endpoints без `training.assign`, добавлен page-level assign CTA с permission fallback; `TaskTable.tsx` переведён с `task.view` на `task.update` / `tasks.write`, а в `TasksPage.tsx` добавлен focused-task close CTA на `task.update`; `DashboardPage.tsx` получил page-level gates для top CTA, а вход в мастер генерации выровнен с route guard на `doc.create`; `ReportsPage.tsx` получил export gating (`doc.export`/`reports.view`); `BriefingsPage.tsx` получил write-action gating по `training.assign`.
**Приоритет страниц:**

1. `IncidentsPage.tsx` — завершено
2. `TasksPage.tsx` / `TaskTable.tsx` — частично завершено, close actions write-gated и выведены в page-level UX для focused task; create/assign flows ещё требуют дальнейшего расширения
3. `TrainingPage.tsx` — частично завершено, teacher surface write-gated и page-level assign CTA добавлен; start-flow и дополнительные assign сценарии ещё требуют расширения
4. `PpePage.tsx` — завершено для quick issue CTA
5. `InspectionsPage.tsx` — завершено
6. `DocumentsPage.tsx` — уже есть, верифицировать
7. `DashboardPage.tsx` — завершено для top CTA
8. `ReportsPage.tsx` — завершено для экспортных CTA
9. `BriefingsPage.tsx` — завершено для ключевых write actions

**Шаблон:**
```tsx
import { Can } from "@/components/permissions/Can";
import { PERMISSIONS } from "@/permissions/permissions";

<Can permission={PERMISSIONS.INCIDENT_CREATE}>
  <Button onClick={onCreateIncident}>Зарегистрировать инцидент</Button>
</Can>
```

---

### B6. Document Readiness Score

**Gap:** DOC-002  
**Файл:** `backend/app/api/routes/documents.py` — добавить endpoint:

```python
@router.get("/{document_id}/readiness")
async def get_document_readiness(document_id: UUID, ...) -> DocumentReadinessResponse:
    ...
```

---

### B7. Queue/Job Diagnostics Endpoints

**Gap:** OPS-008  
**Файл:** `backend/app/api/routes/jobs.py` — расширить:

```
GET /jobs/failed               # failed jobs с причиной
GET /jobs/poisoned             # poisoned jobs
GET /jobs/queue-summary        # pending/running/failed counts
POST /jobs/{id}/retry          # retry failed job
```

---

## Волна C — Data Quality + Field (2-3 спринта)

### C1. DataQualityIssue Model + Migration

**Gap:** OPS-001  
**Файл:** новый `backend/app/models/data_quality.py` + Alembic migration

```python
class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    # ... (см. Plan Phase 6.1)
```

---

### C2. Data Quality Service

**Gap:** OPS-001  
**Файл:** `backend/app/services/data_quality.py`

Checks: employees, companies/sites, templates/documents, training, PPE, contractors.

---

### C3. DQ Celery Job + Endpoints

**Gap:** OPS-001  
**Файлы:** `celery/tasks/data_quality_job.py`, новый `routes/data_quality.py`

---

### C4. Offline Queue Manager

**Gap:** PWA-002  
**Файл:** `frontend/src/components/offline/OfflineQueueManager.tsx`

---

### C5. Local Draft Hook

**Gap:** PWA-003  
**Файл:** `frontend/src/hooks/useLocalDraft.ts`

---

### C6. Offline Field Scenarios

**Gap:** PWA-001  
**Подход:**
1. Briefing mark offline — `BriefingsPage.tsx` + `useLocalDraft`
2. Incident draft offline — `IncidentsPage.tsx` + `useLocalDraft`
3. Background sync через PWA Service Worker Sync API

---

### C7. Bulk Operations — Backend Endpoints

**Gap:** UX-004  
Приоритет:
- `POST /tasks/bulk-update` — bulk complete/reassign
- `POST /training/enrollments/bulk` — bulk enroll
- `POST /ppe/issues/bulk` — bulk issue

---

## Волна D — Reliability + Governance (1-2 спринта)

### D1. Heartbeat/Watchdog

**Gap:** REL-001  
**Файл:** `backend/app/celery/tasks/heartbeat_job.py`

```python
@celery_app.task
def system_heartbeat():
    # check DB, Redis, MinIO
    # write last_heartbeat record
    # notify admin on failure
```

---

### D2. DLQ Cleanup Job

**Gap:** REL-002  
**Файл:** `backend/app/celery/tasks/cleanup_jobs.py`

```python
@celery_app.task
def cleanup_poisoned_jobs(max_age_days: int = 30):
    # archive or alert on poisoned jobs older than max_age_days
```

---

### D3. Celery Retry Audit

**Gap:** REL-003  
Аудит `celery/tasks/*.py` — добавить `autoretry_for=(Exception,)` где отсутствует.

---

### D4. Onboarding Checklist

**Gap:** OPS-006  
**Файл:** новый `routes/admin_onboarding.py`

```
GET /admin/onboarding-checklist
POST /admin/onboarding-checklist/{step}/complete
```

---

### D5. Runbooks

**Gap:** REL-005  
Создать:
- `docs/RUNBOOK_STARTUP.md`
- `docs/RUNBOOK_JOBS.md`
- `docs/RUNBOOK_INTEGRATIONS.md`
- `docs/RUNBOOK_INCIDENTS.md`

---

## Волна E — External Adapters (Будущее, after business decision)

> Эти шаги заблокированы внешними procurement/compliance решениями. Engineering готовность обеспечена через `services/integrations/interfaces.py`.

### E1. Real Signing Provider

Подключить КриптоПро или альтернативный ГОСТ-совместимый провайдер.  
**Interface:** `BaseSigningIntegration` (создать аналогично с `BaseEDOIntegration`)

### E2. Real EDO Operator

Подключить аккредитованный ЭДО-оператор (Диадок, СБИС, Taxcom, etc.)  
**Interface:** уже существует `BaseEDOIntegration`

### E3. WebSocket Transport

Реализовать полноценный WS transport заместо polling fallback.  
**Prerequisite:** Redis Pub/Sub infrastructure, WS-capable deployment (nginx/caddy WS proxy)

### E4. 1C Integration

Подключить реальный 1C adapter.  
**Interface:** уже существует `BaseAccountingIntegration`

---

## Критерии перехода между волнами

| Волна → | Критерий готовности |
|---------|-------------------|
| A → B | Backend authz gaps закрыты, 12 страниц имеют states, `useUnsavedChanges` реализован и применён к wizards |
| B → C | Provider status и tenant health endpoints живые, 5 приоритетных страниц имеют permission gates, workspace role projections работают |
| C → D | Data Quality service запускается и детектирует issues, 1 field scenario (briefing offline) работает end-to-end |
| D → E | Heartbeat job работает, DLQ cleanup настроен, runbooks написаны, onboarding checklist работает |

---

## Чеклист для каждого изменения

Перед merge любого изменения из этого плана:

- [ ] Изменение tenant-aware (tenant_id в WHERE или tenant context в Celery)
- [ ] Изменение permission-aware (abac/rbac или explicit reason для исключения)
- [ ] Audit trail для sensitive actions (write, delete, bulk)
- [ ] Structured error format (`{"code": "...", "message": "..."}`)
- [ ] Correlation ID propagation (в фоновых jobs)
- [ ] Unit/integration тест написан
- [ ] Нет breaking changes в существующих API contracts
- [ ] Нет breaking changes в document lifecycle (upload, preview, PDF, packs)

---

## Контакты и ответственность

| Область | Ответственный |
|---------|--------------|
| Backend security gaps (Волна A) | Backend Engineer |
| Frontend UX states (Волна A) | Frontend Engineer |
| Role workspaces (Волна B) | Full-stack |
| Data Quality (Волна C) | Backend Engineer + PM |
| PWA/Offline (Волна C) | Frontend Engineer |
| External adapters (Волна E) | Engineering + Procurement |

---

*Next Steps документ актуален для планирования Волны A. Обновлять после каждого завершённого milestone.*
