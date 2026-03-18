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
