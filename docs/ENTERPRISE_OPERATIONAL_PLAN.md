# Enterprise Operational Plan

**Дата:** 2026-03-24  
**Версия:** 1.0  
**Основа:** `ENTERPRISE_OPERATIONAL_AUDIT.md` v1.0  
**Принципы:** Без massive rewrite. Фиксировать, усиливать, не ломать.

---

## Введение

Этот план описывает 11 фаз доведения платформы до корпоративного production-ready состояния. Каждая фаза имеет конкретные задачи, критерии готовности и описание рисков.

**Принципы работы:**
1. Каждое изменение — tenant-aware, permission-aware, audit-aware
2. Новая логика должна быть протестирована
3. Stub/deferred — изолировать, задокументировать, не маскировать под production
4. Не ломать: template upload, version history, lint, preview, branding, replace, PDF, packs

---

## PHASE 1 — ENTERPRISE OPERATIONAL AUDIT

**Статус:** ✅ ЗАВЕРШЕНА (данный документ — часть результата)

**Deliverables:**
- [x] `docs/ENTERPRISE_OPERATIONAL_AUDIT.md`
- [x] `docs/ENTERPRISE_OPERATIONAL_PLAN.md` (этот файл)

---

## PHASE 2 — CONSISTENCY HARDENING

**Цель:** Единообразное поведение всей платформы.

### 2.1 Backend: AuthZ Coverage Gap (CRITICAL)

**Проблема:** После закрытия backend-критичных gaps основной перекос сместился в consistency и frontend action-level permissions.

| Файл | Действие |
|------|----------|
| `replace.py` | ✅ Закрыто: `abac()` добавлен для read/write поверх tenant scope |
| `external_registry.py` | ✅ Закрыто: `rbac()` добавлен для всех endpoints |
| `items.py` | Уточнено: пустой router, нужен cleanup, а не security fix |
| `public_api.py` | Уточнено: machine-key API с `api_key_auth` и scope checks; при необходимости усилить rate limiting |

**Критерий готовности:** backend authz-gaps закрыты, дальше приоритет на frontend permission awareness и error normalization.

### 2.2 Backend: Structured Error Format

**Стандарт** (уже используется в большинстве роутов):
```python
{"code": "domain_error_type", "message": "Human-readable message"}
```

**Задача:** Верифицировать, что все routes используют этот формат. Особое внимание на маршрутах без test_*_error_contract.py.

**Роуты без error contract тестов (требуют проверки):**
- `calendar.py`, `journals.py`, `items.py`

### 2.3 Backend: Correlation ID Propagation

**Текущее состояние:** Correlation ID реализован в `core/tracing.py`, propagated в tenancy middleware и RBAC/ABAC forbidden response.

**Задача:** Убедиться что фоновые Celery jobs логируют correlation_id из контекста задачи.

**Файлы:** `celery/tasks/*.py` — проверить использование `task_context.py`

### 2.4 Backend: Audit for Sensitive Actions

**Текущее состояние:** `@audit_operation` используется в 237 местах в routes.

**Задача:** Верифицировать покрытие audit для:
- `replace.py` write-операций (есть `@audit_operation` — ✅)
- Bulk operations (когда появятся)
- Admin actions (user management, role changes)

### 2.5 Frontend: Route-level Permission Awareness

**Задача:** Добавить `PermissionGate`/`Can` обёртку для action-кнопок на приоритетных страницах:
- Документы: Создать документ, Генерировать пакет
- Инциденты: Зарегистрировать инцидент
- Задачи: Создать задачу, Bulk-complete
- СИЗ: Выдать СИЗ
- Обучение: Зачислить на программу
- Проверки: Создать проверку, Закрыть проверку

**Компонент уже есть:** `components/permissions/Can.tsx`, `ActionButton.tsx`, `useAbility.ts`

### 2.6 Frontend: Standard Loading/Error/Empty States

**Приоритетный список страниц без states (из аудита, осталось ~8 страниц):**
1. `RiskPage.tsx` — добавить EmptyState + loading + error
2. `EdoPage.tsx` — добавить EmptyState + loading + error
3. `SignaturesPage.tsx` — добавить EmptyState + loading + error
4. `TemplatesPage.tsx` — добавить EmptyState + loading + error
5. `NpaPage.tsx` — добавить EmptyState + loading + error

**Шаблон:**
```tsx
<ErrorState error={error ?? undefined} onRetry={() => void reload()} />
{loading ? <LoadingScreen label="Загрузка..." /> : null}
{!loading && !error && items.length === 0 ? (
  <EmptyState title="Записи не найдены" description="..." />
) : null}
```

### 2.7 Frontend: Unsaved Changes Protection

**Задача:** Реализовать shared hook `useUnsavedChanges` и применить к:
- `DocumentsWizardPage.tsx`
- `GeneratePackWizardPage.tsx`
- `BrandingSettingsPage.tsx`
- Любые wizard-like формы

**Реализация:**
```ts
// hooks/useUnsavedChanges.ts
export function useUnsavedChanges(isDirty: boolean) {
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) { e.preventDefault(); e.returnValue = ""; }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);
}
```

---

## PHASE 3 — ROLE-BASED WORKSPACES

**Цель:** Пользователь после входа сразу видит что просрочено, что заблокировано, что делать дальше.

### 3.1 Backend: Role-specific Workspace Projections

**Добавить в `workspace.py`:**

```python
@router.get("/role-summary/{role}")
async def role_workspace_summary(role: str, ...) -> RoleWorkspaceSummary:
    ...
```

Роли для реализации:
- `safety_lead` — инциденты, инспекции, проверки, просроченные предписания
- `hr_lead` — медосмотры, обучение, просроченные зачисления
- `line_manager` — задачи по своим сотрудникам, СИЗ выдача
- `contractor_manager` — готовность подрядчиков, просроченные договора

### 3.2 Backend: Unified Task Projection

**Задача:** Унифицировать источники задач в task inbox:
- `obligations.Task` (уже есть)
- Дообавить: просроченные `TrainingEnrollment`, просроченные `PPEIssue`, просроченные `MedicalExam`, overdue `Incident` (без assigned/closed), overdue `Inspection`

**Endpoint:** `/workspace/unified-tasks?role=safety_lead&limit=50`

### 3.3 Backend: Recent Items Projection

```python
@router.get("/recent")
async def workspace_recent(limit: int = 20, ...) -> WorkspaceRecentResponse:
    # Last modified: documents, tasks, incidents, inspections by tenant+user
```

### 3.4 Frontend: Dashboard UX

**Текущее состояние:** `DashboardPage.tsx` уже имеет task inbox + attention panel.

**Усиление:**
- Добавить "что делать сейчас" секцию (приоритизация: critical blockers → overdue tasks → due soon)
- Добавить Recent Items виджет
- Добавить role-контекстный заголовок ("Добро пожаловать, [роль] [имя]")
- Deep links от каждого элемента к нужному экрану с контекстом

---

## PHASE 4 — DOCUMENT CORE AS CENTRAL ENTERPRISE ENGINE

**Цель:** Усилить document core без rewrite. Все working features сохранить.

### 4.1 Template Scope Resolution

**Текущее состояние:** Templates существуют. Scope resolution не верифицирован.

**Задача:** Убедиться что template lookup идёт в порядке: system → tenant → company → site.

**Файл:** `backend/app/modules/templates/` (требует изучения)

### 4.2 Replace Route AuthZ

**Статус:** `replace.py` уже переведён в ABAC-protected режим для read/write операций.

```python
from app.core.security import abac, AccessContext
ReplacerAccess = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=["admin", "employee"], action="replace document"))]
```

### 4.3 Document Readiness Score

**Задача:** Финализировать `/documents/{id}/readiness` endpoint (если не существует — создать).

Структура ответа:
```json
{
  "score": 0.85,
  "max_score": 1.0,
  "level": "ready|partially_ready|blocked",
  "checks": [
    {"code": "template_bound", "passed": true, "impact": 0.2},
    {"code": "header_footer_applied", "passed": true, "impact": 0.1},
    {"code": "pdf_generated", "passed": false, "impact": 0.2, "action": "Generate PDF"},
    {"code": "approval_complete", "passed": false, "impact": 0.3},
    {"code": "signed", "passed": false, "impact": 0.2}
  ]
}
```

### 4.4 NPA → Template Dependency Map

**Задача:** Добавить `/npa/{id}/dependency-map` endpoint:
```json
{
  "npa_id": "...",
  "templates": [...],
  "packages": [...],
  "approval_routes": [...],
  "rules": [...]
}
```

### 4.5 Document Passport Completeness

**Файл:** `core/utils/pdf_passport.py` — верифицировать что passport включает все metadata поля из ТЗ.

---

## PHASE 5 — REMOVE CORPORATE-BLOCKING STUBS

**Цель:** Убрать ложное ощущение production-ready. Не маскировать stub под production.

### 5.1 Явная маркировка non-production режима

**Все stub-провайдеры уже имеют** `provider_mode: non_production` и `adapter_type: stub` — это правильно.

**Задача:** Добавить `/admin/provider-status` endpoint, который явно отображает:
```json
{
  "providers": {
    "signing": {"mode": "non_production", "adapter": "internal-fallback", "warning": "..."},
    "edo": {"mode": "non_production", "adapter": "stub-edo", "warning": "..."},
    "accounting": {"mode": "non_production", "adapter": "stub-1c", "warning": "..."},
    "websocket": {"mode": "non_production", "adapter": "polling_fallback", "warning": "..."}
  },
  "production_ready": false,
  "blocking_for_golive": ["signing", "edo"]
}
```

### 5.2 Approval Orchestration

**Текущее состояние:** `approval_orchestration.py` + `approval_signing_v1.py` используют internal-fallback.

**Задача:**
- Оставить internal orchestration (она реальная и корректная)
- Убедиться что каждый ответ содержит `provider_mode: non_production` явно
- Добавить в admin diagnostics предупреждение если signing не в production mode
- Задокументировать API для подключения реального КриптоПро/продакшн провайдера

### 5.3 EDO Workflow

**Текущее состояние:** `edo_workflow.py` использует `edo_status_simulation_job`.

**Задача:**
- Проверить что simulation job не выглядит как реальная доставка
- Каждый EDO response должен содержать `simulation: true` если это simulation
- Задокументировать adapter interface для реального ЭДО-оператора

### 5.4 WebSocket (ws_stub.py)

**Текущее состояние:** polling fallback уже реализован корректно.

**Задача:** Только документация. Указать в admin diagnostics что реальный WS transport - будущая фаза.

### 5.5 Pipeline Step Handlers

**Текущее состояние:** Большинство шагов — реальные internal implementations. EDO step — stub.

**Задача:** Убедиться что в job timeline отображается `provider_mode` для каждого шага, где используется stub.

---

## PHASE 6 — DATA QUALITY + READINESS BLOCKERS

**Цель:** Data Quality как часть повседневной работы.

### 6.1 Модель DataQualityIssue

**Добавить в модели:**
```python
class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id = Column(UUID, primary_key=True)
    tenant_id = Column(UUID, ForeignKey("tenants.id"))
    entity_type = Column(String)  # employee, company, document, training, ppe
    entity_id = Column(UUID)
    issue_code = Column(String)
    severity = Column(String)  # critical, high, medium, low
    title = Column(String)
    description = Column(String)
    detected_at = Column(DateTime)
    resolved_at = Column(DateTime, nullable=True)
    scenario_impact = Column(JSONB)  # list of scenarios affected
```

### 6.2 DQ Check Service

**Создать:** `backend/app/services/data_quality.py`

Минимальные проверки:
```python
async def check_employees(session, tenant_id) -> list[DataQualityIssue]:
    # missing: position, department, hire_date
    # expired: medical exam, training
    # overdue: briefing

async def check_companies_sites(session, tenant_id) -> list[DataQualityIssue]:
    # missing: address, contact, hazard_class (for fire safety)

async def check_templates_documents(session, tenant_id) -> list[DataQualityIssue]:
    # unbound templates, documents without approval route
    # draft documents older than X days

async def check_training(session, tenant_id) -> list[DataQualityIssue]:
    # overdue enrollments, programs without schedule

async def check_ppe(session, tenant_id) -> list[DataQualityIssue]:
    # issues without issue date, expired norms

async def check_contractors(session, tenant_id) -> list[DataQualityIssue]:
    # expired contracts, missing safety passport
```

### 6.3 DQ Celery Job

**Добавить в `celery/tasks/`:**

```python
@celery_app.task(bind=True)
def run_data_quality_checks(self, tenant_id: str):
    # run all checks, persist issues, update workspace attention
```

**Периодичность:** 1 раз в сутки, trigger on demand через `/admin/data-quality/run`.

### 6.4 DQ API Endpoints

```
GET /admin/data-quality/summary       # by severity counts
GET /admin/data-quality/issues        # paginated list
GET /admin/data-quality/entity/{type}/{id}  # issues for specific entity
POST /admin/data-quality/run          # trigger recheck
```

### 6.5 Интеграция с workspace

**`workspace.py`:** Добавить DQ issues с `severity=critical` в `readiness_blockers`.

---

## PHASE 7 — PWA / OFFLINE / FIELD HARDENING

**Цель:** Реально полезный mobile/field contour.

### 7.1 Bootstrap Reinforcement

**`/api/pwa/bootstrap`** уже возвращает много данных. Усилить:
- Добавить `offline_field_scenarios`: которые сценарии доступны offline для конкретного пользователя
- Добавить `sync_diagnostics`: последний успешный sync, pending items count
- Добавить `conflict_policy`: как разрешаются конфликты (last-write-wins, server-wins)

### 7.2 Offline Queue UX

**Создать компонент:** `components/offline/OfflineQueueManager.tsx`
- Список pending items с типом и временем
- Кнопка "Синхронизировать сейчас"
- Статус последней синхронизации
- Конфликты с action: "Оставить локальную" / "Принять серверную"

### 7.3 Local Draft Persistence

**Создать:** `hooks/useLocalDraft.ts`
```ts
function useLocalDraft<T>(key: string, initial: T): [T, (v: T) => void, clearDraft: () => void]
// Uses IndexedDB via idb-keyval or localStorage for small drafts
```

**Применить к:**
- `BriefingsPage.tsx` — briefing draft mark
- `IncidentsPage.tsx` — incident draft registration
- Inspection checklist completion

### 7.4 Field Scenarios Support

| Сценарий | Требование |
|----------|-----------|
| Briefing/instruction mark | Offline form с локальным сохранением, sync при reconnect |
| Incident draft | Offline регистрация с медиа/фото |
| Checklist completion | Checkpoint-based save, resume on reconnect |
| Task comment | Offline capture, sync queue |
| Photo/media sync | Background sync через Service Worker Sync API |
| Training acknowledgement | Offline подтверждение с timestamp |

### 7.5 Sync Diagnostics для пользователей

**Добавить в DashboardPage/Settings:**
- "Последняя синхронизация: 5 минут назад"
- "Ожидает синхронизации: 3 записи"
- "Конфликты: 1 (требует решения)"

---

## PHASE 8 — OPERATIONAL UX HARDENING

**Цель:** Довести приоритетные страницы до daily-use usability без rewrite.

### 8.1 Приоритет 1 — Критические страницы с gaps

Для каждой из следующих страниц применить шаблон Consistency pass из Phase 2.6:

**`RiskPage.tsx`** — добавить:
- EmptyState: "Оценки рисков не найдены. Создайте первую оценку."
- Loading + Error states
- Next action кнопка: "Новая оценка риска"
- Blockers: высокие риски без митигации

**`EdoPage.tsx`** — добавить:
- EmptyState: "ЭДО сообщения отсутствуют"
- Loading + Error + provider mode warning (non_production)
- Status badges

**`WorkflowPage.tsx`** — добавить:
- EmptyState + Error
- Workflow status summary

**`SignaturesPage.tsx`** — добавить:
- EmptyState/loading/error
- Provider mode indicator (non-production signing)

**`TemplatesPage.tsx`** — добавить:
- Loading/error/empty states
- "Загрузить шаблон" как primary CTA

**`NpaPage.tsx`** — добавить:
- EmptyState + loading/error
- Indicator "Изменений с прошлой проверки: N"

### 8.2 Приоритет 2 — Firebase и inspection pages

**Статус:** ✅ ЗАВЕРШЕНО (loading/error/empty + contextual next actions/blockers добавлены)

**`FireInspectionsPage.tsx`, `FireTrainingPage.tsx`, `InspectionChecklistsPage.tsx`, `InspectionPlansPage.tsx`, `InspectionPrepPackagesPage.tsx`:**
- Verify loading/error/empty pattern (если не хватает — добавить)
- Добавить next action для overdue items
- Добавить blockers/readiness context

### 8.3 Приоритет 3 — Dashboard variants

**Статус:** ✅ ЗАВЕРШЕНО (shared `DashboardApiPage` переведён на explicit loading/error/empty shell)

**`SafetyDashboardPage.tsx`, `TrainingDashboardPage.tsx`, `ClientDeliveryDashboardPage.tsx`:**
- Добавить loading/error states
- Операционный KPI (не статические карточки)

### 8.4 Шаблон "Next Action"

Стандартная структура для "что делать дальше":
```tsx
{overdueItems.length > 0 && (
  <Alert variant="destructive">
    <ShieldAlert className="h-4 w-4" />
    <AlertTitle>{overdueItems.length} записей просрочено</AlertTitle>
    <AlertDescription>
      <Button variant="link" asChild>
        <Link to="/tasks?filter=overdue">Показать просроченные →</Link>
      </Button>
    </AlertDescription>
  </Alert>
)}
```

---

## PHASE 9 — ENTERPRISE ADMIN / GOVERNANCE / DIAGNOSTICS

### 9.1 Tenant Health Endpoint

**Добавить:** `GET /admin/tenant-health`
```json
{
  "tenant_id": "...",
  "health_score": 0.78,
  "checks": {
    "data_quality": {"score": 0.6, "issues": 12},
    "integration_readiness": {"score": 0.4, "non_production_providers": 4},
    "pending_approvals": {"count": 3, "overdue": 1},
    "failed_jobs": {"count": 0},
    "outbox_pending": {"count": 5},
    "onboarding_complete": false,
    "onboarding_missing": ["branding", "first_template"]
  }
}
```

### 9.2 Provider Mode Diagnostics

**Добавить:** `GET /admin/provider-status`

(см. Phase 5.1 — явная маркировка)

### 9.3 Queue/Job Diagnostics

**`jobs.py`** — расширить до:
```
GET /jobs/queue-summary        # pending, running, failed by queue
GET /jobs/failed               # failed jobs with retry info
GET /jobs/poisoned             # poisoned jobs
POST /jobs/{id}/retry          # retry failed job
```

### 9.4 Feature/Module Enablement

**Добавить:** `GET /admin/features`

Список модулей с enabled/disabled статусом, tier и условием включения.

### 9.5 Startup Readiness / Onboarding

**Добавить:** `GET /admin/onboarding-checklist`
```json
{
  "completed_steps": ["branding", "first_user"],
  "pending_steps": ["first_template", "approval_route", "site_setup"],
  "completion_percent": 40
}
```

### 9.6 Admin Frontend Upgrade

**`AdminPage.tsx`** — расширить до:
- Tenant health score с drill-down
- Provider mode warnings (если non-production)
- Queue/job summary widget
- Onboarding checklist
- Feature flags visibility
- Data quality summary

---

## PHASE 10 — RELIABILITY / OBSERVABILITY / RUNBOOKS

### 10.1 Retry Consistency

**Задача:** Верифицировать что все Celery tasks используют `autoretry_for`, `max_retries`, `retry_backoff`.

**Файлы:** `celery/tasks/*.py`

### 10.2 DLQ / Poison Handling

**Текущее состояние:** `POISONED` status есть в `job_engine.py`.

**Задача:** Добавить Celery task `cleanup_poisoned_jobs` — архивировать или уведомлять admin о poisoned jobs старше N дней.

### 10.3 Heartbeat/Watchdog

**Добавить:** Celery beat task `workers_heartbeat` каждые 5 минут:
- ping Redis
- ping DB
- ping MinIO
- write heartbeat record
- если failure — trigger admin notification

### 10.4 Health Endpoint Extension

**Текущее состояние:** `/health` проверяет Postgres, Redis, MinIO, ClamAV, LibreOffice.

**Задача:** Добавить в `/health`:
- Celery worker status
- Outbox pending count
- Last job execution time

### 10.5 Runbooks

**Создать или обновить:**
- `docs/RUNBOOK_STARTUP.md` — локальный запуск, docker-compose
- `docs/RUNBOOK_INCIDENTS.md` — как реагировать на типичные инциденты
- `docs/RUNBOOK_JOBS.md` — управление failed jobs, DLQ
- `docs/RUNBOOK_INTEGRATIONS.md` — подключение реальных провайдеров

---

## PHASE 11 — TESTS

**После каждой волны изменений:**

### 11.1 Backend тесты

| Покрытие | Приоритет |
|---------|----------|
| `replace.py` AuthZ — regression coverage после добавления ABAC | CRITICAL |
| `external_registry.py` AuthZ — regression coverage после добавления RBAC | HIGH |
| `workspace.py` unified-tasks projection | HIGH |
| `data_quality.py` service unit tests | HIGH |
| `admin/tenant-health` endpoint | MEDIUM |
| `admin/provider-status` endpoint | MEDIUM |
| DQ Celery job tenant isolation | HIGH |

### 11.2 Frontend тесты

| Тест | Приоритет |
|-----|----------|
| `useUnsavedChanges` hook unit test | HIGH |
| `useLocalDraft` hook unit test | HIGH |
| `OfflineQueueManager` component | MEDIUM |
| Permission-aware button visibility (per role) | HIGH |
| Empty/loading/error states для foundation pages | MEDIUM |

### 11.3 Contract / Integration тесты

| Тест | Приоритет |
|-----|----------|
| PWA bootstrap completeness contract | HIGH |
| Document readiness score contract | HIGH |
| DQ issue severity escalation to workspace | MEDIUM |
| Tenant health score composition | MEDIUM |

---

## Приоритизация волн

### Волна A (Немедленно — критические безопасность/authz gaps)

1. Добавить loading/error/empty states на 12 foundation pages (UX)
2. Реализовать `useUnsavedChanges` hook + применить к wizards (UX)
3. Доточить error normalization для `calendar.py` / `journals.py`
4. Начать action-level permissions на приоритетных страницах

### Волна B (Корпоративное удобство)

1. Role-based workspace projections backend
2. Unified task inbox backend
3. Action-level permissions на приоритетных страницах frontend
4. provider-status admin endpoint
5. tenant-health admin endpoint

### Волна C (Data Quality + Field)

1. DataQualityIssue model + service
2. DQ endpoints
3. OfflineQueueManager component
4. useLocalDraft hook
5. Field scenario support (briefings, incidents, checklists)

### Волна D (Reliability + Operational Maturity)

1. Heartbeat/watchdog
2. DLQ cleanup jobs
3. Queue diagnostics API
4. Onboarding checklist
5. Runbooks update

### Волна E (External adapters — будущее)

1. КриптоПро/реальный signing provider
2. Реальный ЭДО-оператор
3. WebSocket transport
4. 1C integration

---

## Риски и ограничения

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| Rewrite drift — изменения ломают working flows | Средняя | Тесты перед деплоем каждой волны |
| DataQualityIssue table migration — таблица новая | Низкая | Alembic migration с down-revision |
| Role workspace projections — тяжёлые queries | Средняя | Индексы + кэш на Redis |
| External providers никогда не подключат | Высокая | Изоляция стабильна, контракт API задокументирован |
| Frontend permission gates — мешают пользователям | Низкая | Скрывать кнопки, а не ломать URL |

---

*Plan составлен на основе аудита 2026-03-24. Обновлять после каждой завершённой волны.*
