# GAP Report (2026-03-18 targeted increment)

## Что найдено
- `backend/app/api/routes/client_portal.py` был в аварийном состоянии: дублированные фрагменты, незакрытые скобки и сломанный синтаксис блокировали production-use и тесты.
- Domain-слой для `templating`, `replace`, `packs`, `files/document`, `npa/compliance` оставался слишком thin/stub и не давал воспроизводимые metadata / persisted patch journal / usable portal artifacts.
- Тестовое покрытие не фиксировало portal history/tickets и не проверяло явно факт появления `IncidentCreated` / `InspectionCreated` в outbox после API create-flow.

## Что исправлено
- Полностью восстановлен и нормализован `client_portal` API flow: preset -> run -> artifacts -> portal link -> files/history -> tickets.
- `TemplateRenderer` усилен reproducibility metadata, fallback-render предупреждениями и детерминированными context hashes.
- `ReplaceEngine` доведён до persisted patch storage уровня domain-layer: dry-run/apply/rollback теперь сохраняют patch journal, diff, audit fields и статус rollback.
- `FileStorageService` расширен safe temp-file workflow и S3-compatible adapter wiring, при этом dev/test memory/local режимы сохранены без обязательного MinIO.
- `DocumentService`, `PackAssembler`, `ComplianceChecker` усилены metadata / signed-download / impact-analysis/useful warnings.
- Добавлены регрессионные тесты на portal artifacts/history/tickets, persisted replace patches и outbox events для incidents/inspections.

## Что осталось как осознанный backlog P2
- Перенести replace patch journal из file-backed domain storage в shared DB storage для multi-worker rollback.
- Дотянуть frontend client portal/package wizard до enterprise UX уровня (rich selectors, timeline panels, retry UX).
- Довести PDF pipeline до полного acceptance scope по hanging detection/font embedding/retry telemetry.
- Расширить briefings по overdue notifications/UI и prescription overdue corrective events.
