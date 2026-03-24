# Enterprise Operational Remaining Gaps

**Дата:** 2026-03-24  
**Версия:** 1.0  
**Основа:** Аудит кода + ENTERPRISE_OPERATIONAL_AUDIT.md

---

## Формат записи

Каждый gap описан по схеме:
- **Что:** описание проблемы
- **Где:** точный файл/модуль
- **Почему critical:** влияние на бизнес
- **Effort:** оценка трудозатрат
- **Blocker for:** что блокирует

---

## КАТЕГОРИЯ 1: SECURITY / AUTHZ GAPS

### GAP-SEC-001 — `items.py` пустой router без явного решения
- **Что:** `backend/app/api/routes/items.py` не содержит endpoints. Security-риска сейчас нет, но граница модуля не определена: либо удалить, либо наполнить и защитить.
- **Где:** `/workspaces/prt_ot_doc/backend/app/api/routes/items.py`
- **Почему важно:** Мёртвые module boundaries создают ложное ощущение незавершённости и мешают аудиту покрытия.
- **Effort:** XS
- **Blocker for:** Волна B

---

## КАТЕГОРИЯ 2: FRONTEND UX GAPS

### GAP-UX-001 — Action-level permission gates отсутствуют на ~70 страницах
- **Что:** Permission gates уже добавлены на приоритетных operational страницах (incidents/inspections/tasks/training/ppe/dashboard/reports/briefings/documents + pipeline pages), но systematic coverage по всем action-CTA всё ещё не завершён. Кнопки "Создать", "Удалить", "Экспортировать" остаются видимыми на части экранов вне приоритетной волны.
- **Где:** Все `frontend/src/pages/**/*.tsx` кроме документов и pipeline pages
- **Почему critical:** Пользователи с read-only доступом видят write-операции → confusion, ошибки, потенциальные 403 errors без UI feedback.
- **Effort:** L (systematic pass по ~70 страницам)
- **Blocker for:** Волна B

### GAP-UX-002 — Unsaved changes protection отсутствует
- **Что:** Базовый `useUnsavedChanges` уже реализован и подключён к `DocumentsWizardPage.tsx`, `GeneratePackWizardPage.tsx`, `BrandingSettingsPage.tsx`, но остальные формы/wizards ещё без защиты.
- **Где:** `DocumentsWizardPage.tsx`, `GeneratePackWizardPage.tsx`, `BrandingSettingsPage.tsx` + все другие формы
- **Почему critical:** Корпоративные пользователи теряют данные при заполнении сложных форм — прямая потеря продуктивности.
- **Effort:** S-M (распространить hook на оставшиеся формы)
- **Blocker for:** Волна A

### GAP-UX-003 — ~8 страниц без loading/error/empty states
- **Что:** Foundation pages отображают пустое состояние или сломанный UI при loading/error.
- **Где:** `RiskPage.tsx`, `EdoPage.tsx`, `SignaturesPage.tsx`, `TemplatesPage.tsx`, `NpaPage.tsx`, `PortalRequestsPage.tsx`, `SafetyDashboardPage.tsx`, `TrainingDashboardPage.tsx`, `ClientDeliveryDashboardPage.tsx` + другие
- **Почему critical:** Корпоративные пользователи не понимают состояние системы — неуверенность, повторные нажатия, escalation.
- **Effort:** M (шаблонный, повторяющийся)
- **Blocker for:** Волна A

### GAP-UX-004 — Bulk operations отсутствуют
- **Что:** Нет UI для bulk selection. В backend только `briefings/entries/bulk-create`. Нет bulk close tasks, bulk assign training, bulk issue PPE.
- **Где:** Весь frontend; backend routes
- **Почему critical:** Корпоративные HR/safety leads работают с сотнями записей — без bulk operations ежедневное использование непрактично.
- **Effort:** L (backend endpoints + frontend UI)
- **Blocker for:** Волна C

## КАТЕГОРИЯ 3: OPERATIONAL CAPABILITY GAPS

### GAP-OPS-001 — Data Quality модуль отсутствует
- **Что:** Нет `DataQualityIssue` модели, нет DQ service, нет DQ endpoints, нет DQ dashboard. Partial проверки в workspace blockers, но не персистируются.
- **Где:** Backend — нет модуля, нет endpoints; Frontend — нет DQ dashboard
- **Почему critical:** Корпоративные платформы должны автоматически детектировать incomplete/expired/conflicting данные. Без DQ — ручной audit-зависимость.
- **Effort:** XL (новый модуль — модели, миграция, сервис, endpoints, celery job, frontend)
- **Blocker for:** Волна C

### GAP-OPS-002 — Role-specific workspace projections отсутствуют
- **Что:** Единый `/workspace/attention` для всех ролей. Нет safety_lead / hr_lead / line_manager / contractor_manager проекций.
- **Где:** `backend/app/api/routes/workspace.py`, `frontend/src/pages/dashboard/`
- **Почему critical:** Safety lead и HR видят одно и то же — нет role-specific task prioritization. Operational неэффективность.
- **Effort:** M
- **Blocker for:** Волна B

### GAP-OPS-003 — Unified task projection не охватывает все источники
- **Что:** Task inbox агрегирует только `Task` модель. Overdue `TrainingEnrollment`, `PPEIssue`, `MedicalExam`, просроченные `Incident` без assignee — не включены.
- **Где:** `backend/app/api/routes/workspace.py` — метод `workspace_task_inbox`
- **Effort:** M
- **Blocker for:** Волна B

### GAP-OPS-004 — Tenant health score endpoint отсутствует
- **Что:** Нет `GET /admin/tenant-health` с комплексной оценкой здоровья tenant.
- **Где:** Backend — нет endpoint; Frontend `AdminPage.tsx` — нет виджета
- **Effort:** M
- **Blocker for:** Волна B

### GAP-OPS-005 — Provider status endpoint отсутствует
- **Что:** Нет `/admin/provider-status` с явным перечислением production/non-production провайдеров.
- **Где:** Backend — нет endpoint
- **Почему critical:** Admin не видит что в production mode, а что — stub. Невозможно оценить go-live readiness.
- **Effort:** S
- **Blocker for:** Волна B

### GAP-OPS-006 — Onboarding checklist отсутствует
- **Что:** Нет `/admin/onboarding-checklist` — новый tenant не знает что нужно настроить для первого запуска.
- **Где:** Backend и Frontend
- **Effort:** M
- **Blocker for:** Волна D

### GAP-OPS-007 — Feature/module enablement visibility отсутствует
- **Что:** Нет явного `GET /admin/features` endpoint с enabled/disabled модулями.
- **Effort:** S
- **Blocker for:** Волна D

### GAP-OPS-008 — Queue/job diagnostics endpoint неполный
- **Что:** `jobs.py` существует, но без `queue-summary`, `failed`, `poisoned` sub-endpoints.
- **Effort:** M
- **Blocker for:** Волна B

---

## КАТЕГОРИЯ 4: PWA / OFFLINE GAPS

### GAP-PWA-001 — Offline field scenarios не реализованы
- **Что:** Нет offline briefing mark, incident draft, checklist completion, task comment, photo sync.
- **Где:** `frontend/src/pages/briefings/`, `incidents/`, `inspection-checklists/`
- **Почему critical:** Field workers без offline scenarios бесполезны при работе на объектах без стабильного интернета.
- **Effort:** XL (Service Worker sync, IndexedDB, conflict handling)
- **Blocker for:** Волна C

### GAP-PWA-002 — OfflineQueueManager компонент отсутствует
- **Что:** Нет UI для просмотра и управления offline queue. `ConnectivityBanner.tsx` — только баннер.
- **Effort:** M
- **Blocker for:** Волна C

### GAP-PWA-003 — Local draft persistence hook отсутствует
- **Что:** Нет `useLocalDraft` hook. Формы не сохраняют прогресс локально.
- **Effort:** S
- **Blocker for:** Волна C

### GAP-PWA-004 — Conflict resolution UX отсутствует
- **Что:** При offline/online конфликте нет UI для выбора "локальная" vs "серверная" версия.
- **Effort:** M
- **Blocker for:** Волна C

---

## КАТЕГОРИЯ 5: RELIABILITY / OBSERVABILITY GAPS

### GAP-REL-001 — Heartbeat/watchdog отсутствует
- **Что:** Нет Celery Beat task для периодических health проверок. Нет самодиагностики системы.
- **Effort:** S
- **Blocker for:** Волна D

### GAP-REL-002 — DLQ / Poison cleanup job отсутствует
- **Что:** POISONED status в job_engine.py существует, но нет cleanup/notification job. Poisoned jobs накапливаются.
- **Effort:** S
- **Blocker for:** Волна D

### GAP-REL-003 — Celery retry consistency не верифицирована
- **Что:** Не проверено что все Celery tasks используют `autoretry_for`, `max_retries`, `retry_backoff`. Часть может выполняться без retry при transient failures.
- **Effort:** M (аудит + фиксы)
- **Blocker for:** Волна D

### GAP-REL-004 — Health endpoint не включает Celery worker status
- **Что:** `/health` проверяет Postgres, Redis, MinIO, ClamAV, LibreOffice, но не статус Celery workers.
- **Effort:** S
- **Blocker for:** Волна D

### GAP-REL-005 — Runbooks неполные
- **Что:** В `docs/` есть множество документов, но нет `RUNBOOK_STARTUP.md`, `RUNBOOK_JOBS.md`, `RUNBOOK_INTEGRATIONS.md`.
- **Effort:** M (документирование)
- **Blocker for:** Волна D

---

## КАТЕГОРИЯ 6: ARCHITECTURE DEBT

### GAP-ARCH-001 — `models/models.py` монолит (2784 строки)
- **Что:** Основная масса SQLAlchemy моделей в одном файле. Частичная декомпозиция есть (отдельные `models/workflow.py`, `models/document.py`), но не завершена.
- **Почему gap (не critical):** Не влияет на runtime поведение, но делает onboarding разработчиков сложнее.
- **Effort:** XL (рефакторинг с риском циклических импортов)
- **Blocker for:** Волна E (будущее)

### GAP-ARCH-002 — `tasks.py` mixed domains (1720 строк)
- **Что:** Celery tasks для разных доменов в одном файле. `celery/tasks/` существует и частично использован, но основной объём — в `tasks.py`.
- **Effort:** L (разделение по доменам)
- **Blocker for:** Волна E (будущее)

### GAP-ARCH-003 — `app/domains/` vs `app/modules/` — дублирование
- **Что:** Два слоя доменной логики с разными конвенциями. Нет чёткого правила что куда.
- **Effort:** M (документирование + конвенция)
- **Blocker for:** Волна E (будущее, документация может быть быстрой)

### GAP-ARCH-004 — Tenant context в трёх местах
- **Что:** `app/core/tenancy.py`, `app/core/tenant.py`, `app/tenancy/` — три точки tenant context без чёткой иерархии.
- **Effort:** M (документирование + consolidation)
- **Blocker for:** Волна E (будущее)

---

## КАТЕГОРИЯ 7: DOCUMENT CORE GAPS

### GAP-DOC-001 — Replace route без RBAC (cross-reference с GAP-SEC-001)
- Дублируется в SEС категории. SEС-001 — первичный.

### GAP-DOC-002 — Document Readiness Score endpoint отсутствует
- **Что:** Нет `/documents/{id}/readiness` endpoint со структурированным score и recommended actions.
- **Effort:** M
- **Blocker for:** Волна B

### GAP-DOC-003 — NPA → Template dependency map отсутствует
- **Что:** Нет `/npa/{id}/dependency-map` endpoint.
- **Effort:** M
- **Blocker for:** Волна B

### GAP-DOC-004 — Archive endpoint отсутствует
- **Что:** Нет явного archive flow (document → archived status + index update).
- **Effort:** M
- **Blocker for:** Волна C

### GAP-DOC-005 — Template scope resolution не верифицирована
- **Что:** system → tenant → company → site lookup не подтверждён тестами.
- **Effort:** S (audit + тест)
- **Blocker for:** Волна B

---

## Сводная таблица gap по приоритету и волне

| ID | Описание | Severity | Волна | Effort |
|----|----------|----------|-------|--------|
| SEC-001 | items.py пустой router без явного решения | LOW | B | XS |
| UX-002 | Unsaved changes protection | HIGH | A | M |
| UX-003 | 20 страниц без states | HIGH | A | M |
| UX-001 | Action-level permissions | HIGH | B | L |
| OPS-002 | Role workspace projections | HIGH | B | M |
| OPS-003 | Unified task projection | MEDIUM | B | M |
| OPS-004 | Tenant health score | MEDIUM | B | M |
| OPS-005 | Provider status endpoint | HIGH | B | S |
| OPS-008 | Queue/job diagnostics | MEDIUM | B | M |
| DOC-002 | Document readiness score | MEDIUM | B | M |
| DOC-003 | NPA dependency map | LOW | B | M |
| DOC-005 | Template scope verification | MEDIUM | B | S |
| UX-004 | Bulk operations | MEDIUM | C | L |
| OPS-001 | Data Quality модуль | HIGH | C | XL |
| PWA-001 | Offline field scenarios | HIGH | C | XL |
| PWA-002 | OfflineQueueManager | MEDIUM | C | M |
| PWA-003 | Local draft persistence | MEDIUM | C | S |
| PWA-004 | Conflict resolution UX | MEDIUM | C | M |
| DOC-004 | Archive endpoint | LOW | C | M |
| REL-001 | Heartbeat/watchdog | MEDIUM | D | S |
| REL-002 | DLQ cleanup job | MEDIUM | D | S |
| REL-003 | Celery retry consistency | MEDIUM | D | M |
| REL-004 | Health endpoint + Celery | LOW | D | S |
| REL-005 | Runbooks | LOW | D | M |
| OPS-006 | Onboarding checklist | LOW | D | M |
| OPS-007 | Feature flags visibility | LOW | D | S |
| ARCH-001 | models.py монолит | LOW | E | XL |
| ARCH-002 | tasks.py смешанные домены | LOW | E | L |
| ARCH-003 | domains vs modules | LOW | E | M |
| ARCH-004 | Tenant context в 3 местах | LOW | E | M |

---

*Последнее обновление: 2026-03-24. Обновлять по мере закрытия gaps.*
