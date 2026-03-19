# GAP Report (2026-03-18 targeted increment)

## Что найдено
- `backend/app/api/routes/client_portal.py` был в аварийном состоянии: дублированные фрагменты, незакрытые скобки и сломанный синтаксис блокировали production-use и тесты.
- Domain-слой для `templating`, `replace`, `packs`, `files/document`, `npa/compliance` оставался слишком thin/stub и не давал воспроизводимые metadata / persisted patch journal / usable portal artifacts.
- Тестовое покрытие не фиксировало portal history/tickets и не проверяло явно факт появления `IncidentCreated` / `InspectionCreated` в outbox после API create-flow.
- CRUD-модуль briefings существовал, но не обеспечивал production-grade lifecycle: typed payloads, идемпотентные подписи, audit trail и overdue reminder flow через outbox отсутствовали.

## Что исправлено
- Полностью восстановлен и нормализован `client_portal` API flow: preset -> run -> artifacts -> portal link -> files/history -> tickets.
- `TemplateRenderer` усилен reproducibility metadata, fallback-render предупреждениями и детерминированными context hashes.
- `ReplaceEngine` доведён до persisted patch storage уровня domain-layer: dry-run/apply/rollback теперь сохраняют patch journal, diff, audit fields и статус rollback.
- `FileStorageService` расширен safe temp-file workflow и S3-compatible adapter wiring, при этом dev/test memory/local режимы сохранены без обязательного MinIO.
- `DocumentService`, `PackAssembler`, `ComplianceChecker` усилены metadata / signed-download / impact-analysis/useful warnings.
- Добавлены регрессионные тесты на portal artifacts/history/tickets, persisted replace patches и outbox events для incidents/inspections.
- Briefings переведены из CRUD-only в управляемый lifecycle: typed API payloads, идемпотентные employee/instructor signatures, complete-flow с `valid_until`, overdue listing и `TaskOverdue` reminders через outbox.
- Frontend получил отдельный экран инструктажей и usable client portal cabinet по пакетам: summary/files/history/requests теперь питаются от реального package detail API без dashboard-заглушек; incidents/inspections перестали требовать ручной ввод UUID компании в критичном create-flow.

## Что осталось как осознанный backlog P2
- Перенести replace patch journal из file-backed domain storage в shared DB storage для multi-worker rollback.
- Дотянуть frontend client portal/package wizard до enterprise UX уровня (rich selectors, ticket creation inline, retry UX и richer timeline filters).
- Довести PDF pipeline до полного acceptance scope по hanging detection/font embedding/retry telemetry.
- Закрыть prescription overdue / corrective events и углубить briefings до person/site selectors + background reminder worker.


## Дополнительно в этой волне
- Workflow/BPM v1 усилен версионированием публикаций: новая published-версия автоматически архивирует прошлую published-версию без ломки уже запущенных инстансов; в UI добавлен JSON-driven editor/validator и более подробная instance timeline.
- Notifications Center расширен серверным unread counter API и фильтрами по channel/priority/type в едином экране.
- Global Search получил не только foundation для recent/saved searches, но и расширенную индексацию: компании, площадки, инциденты, проверки, предписания, НПА, договоры, заказы, plan/workflow tasks теперь индексируются в общем search service с facet counts и alias-мэппингом типов.
- NPA UI доведён до detail/impact режима: ревизии, summary по binding-ам и action на создание update tasks теперь доступны из одной страницы.
- Integration reliability UX выведен из stub-состояния: экран `Интеграции` теперь показывает реальную delivery history по outbox/outbox-events, failure states и действия retry/requeue без ручного перехода в админские обходные страницы.

## Осталось backlog после этой волны
- Workflow: системный beat для SLA sweep + ABAC rule-based assignee resolution + richer condition DSL.
- Notifications: delivery history по транспортам, digest scheduler, escalation matrix execution.
- Search: полнота индексации по document/risk/PPE/training read-моделям и ranking tuning на PostgreSQL FTS.
- NPA: более глубокие binding-и для checklist/package/process scopes и массовая актуализация связанных сущностей.
- Integrations: connector-specific health metrics, inbound webhook replay/signature visibility и корреляция статусов по адаптерам (EDO/1C/FRDO/EISOT) всё ещё backlog.

- Дополнительно после финального pass: workflow service исправлен для корректных delegate/escalate режимов и role-aware completion/reassignment; добавлен regression test на timeline событий делегирования/эскалации.
- Search Center расширен enterprise-tabs (`tasks`, `npa`, `contracts`, `orders`) и показом metadata tags/snippets без смены backend contract.
- Для NPA detail добавлен linked entities panel с явным списком binding-ов, а не только summary-счётчиками.
- Для integration admin UX добавлен статусный фильтр delivery history.
- Добавлен PWA/mobile readiness foundation: глобальный offline banner + sync/retry status в shell без перезагрузки приложения.

- Workflow/BPM: поверх уже реализованного engine добавлен registry/list endpoint для workflow instances с open-task counters и status/entity фильтрами, чтобы карточки/реестры могли показывать живые инстансы без ручной навигации в detail view.
- Search: глобальный поиск теперь отдаёт не только `type_counts`, но и `status/company/site` facets, что закрывает часть enterprise faceted-search сценариев без смены storage strategy.
- Analytics/Reporting: расширен backend dashboard layer реальными endpoint-ами `incidents`, `inspections`, `prescriptions`, `overdue`, `sla-load`, `edo`; Reports UI переведён на async Export Center flow вместо вызова отсутствующего `/reports/export`.
- Notifications Center доведён до более операционного режима: API теперь явно отдаёт `is_read`/`deeplink`, а UI поддерживает фильтр по статусу, выборку нескольких записей и bulk mark-read для unread уведомлений без ручного reload.
- Search Center получил видимую faceted-search панель для `status/company/site`, а сохранённые поиски теперь сохраняют и восстанавливают активные фильтры tenant-safe способом.
- Workflow UI закрывает ещё один критичный сценарий enterprise UX: кроме publish доступны archive/reassign действия, а карточка инстанса показывает correlation-id и JSON context для расследования переходов и async-узлов.

Осталось backlog:
- Scheduled reports, digest notifications scheduler, transport-level notification delivery history и полноценные template registries всё ещё требуют отдельного прохода.
- Export Center пока даёт foundation/idempotent async jobs, но без full XLSX/PDF generator pipeline и без anonymized export presets.


## Delta after 2026-03-18 production-minded pass
- Search service hardening: `total` now counts the full filtered result-set instead of page size, and faceted filters were extended to `project_id` / `risk_level` for safer enterprise narrowing in a single tenant-scoped query path.
- Workflow ops hardening: added explicit Celery entrypoint `workflow.sla.tick` so SLA escalations are not only modeled in the service layer but also schedulable via the worker fleet.
- Shell UX hardening: top navigation badges no longer use static placeholders; they poll live workflow-task and unread-notification counters so operators can trust header quick actions.
- Search Center UX hardening: added quick facet chips for site/project/risk level and preserved these filters in saved searches, reducing manual copy/paste of identifiers.

## Enterprise v2.0 additions in this increment
- LMS foundation upgraded from registry-only to teacher/learner cabinet architecture: lessons/materials, progress %, completion confirmation, retake/runtime result ingestion and SCORM/xAPI/proctoring-ready contracts were added on top of existing training entities.
- Advanced risk layer now exposes dedicated enterprise methodology/map APIs over the existing safety-core tables, including Fine-Kinney scoring, residual-risk recalculation, overdue measure visibility and summary links to incident/corrective pressure.
- Export Center moved from async-job-only to BI/DWH-ready foundation: dataset code, schema version, anonymized mode, webhook target contract, schedules and KPI definitions are now persisted.
- Public/machine access got a tenant-scoped machine-key management slice with usage counters/revoke metadata and stable public read contracts for core registries.
- RU-first / EN-ready i18n was extended to the new training/export surfaces, and marketplace catalog foundation was added for publish/install/version/compatibility metadata.
- Follow-up hardening in this pass: public API contracts were normalized around `limit/offset/sort_by/sort_order`, machine-key rotation was added, export schedules became schema-version-aware, custom weighted risk methodologies can be cloned/activated, and package-preset marketplace items can now be materialized into tenant runtime presets.
- Stability hotfix after the main enterprise wave: the NPA detail/task endpoints were brought back to valid FastAPI dependency signatures, and the risk methodology enum/migration were aligned with the already-implemented custom weighted methodology flow so the advanced risk API no longer 500s when persisting `custom` methodologies.

## Осталось после этого этапа
- Реальный worker execution для scheduled exports / webhook callbacks / DWH sinks и более детальная delivery journal UI.
- Полная material player UX для LMS (video/file viewers, richer learner cabinet timeline, certificate rendering and teacher grading workflows).
- Глубже автоматизировать влияние incidents / corrective actions / NPA bindings на persisted residual-risk recalculation, а не только на summary/context layer.
- Marketplace: broader materialization/import-copy beyond package presets, moderation, public storefront UX.
- Backend i18n: локализация structured errors и notification/document templates beyond the new foundation.
- Workflow governance hardening: graph validation now blocks unreachable/orphan nodes and missing terminal paths before publish/start, and human-task complete/reassign/delegate/escalate actions emit dedicated audit events for immutable transition traceability.
- Notifications hardening: tenant-scoped notification templates were added as a reusable platform foundation for in-app/email/telegram/webhook channels, and the unified Notifications Center now exposes that registry alongside preferences/read-state controls.
- NPA impact hardening: detail flow now supports revision-scoped analysis, while update-task generation deduplicates already-open tenant tasks to keep actualization queues retry-safe.
- Regression coverage updated: added focused backend tests for workflow validation, NPA impact task deduplication, and notification template persistence.
