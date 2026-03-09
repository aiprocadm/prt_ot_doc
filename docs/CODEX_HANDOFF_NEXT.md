# CODEX_HANDOFF_NEXT

## Что это за проект
B2B SaaS по ОТ/ПБ/ПромБез с multi-tenant API, документным конвейером (template->replace->pdf->approval/sign/edo), safety вертикалями и клиентским порталом.

## Фактическое состояние
- Базовый скелет платформы реализован (backend+frontend+tests+docs).
- Критичные security/reliability проверки присутствуют в тестах и объединены в `make codex-audit`.
- В этой задаче усилен file-tenant key guard (поддержка legacy + защита от traversal) и обновлен audit-пакет документации.

## Что уже есть (кратко)
- Tenant middleware, RBAC/ABAC, audit, idempotency, outbox/webhooks.
- Модули: templates/replace/pdf/pipelines, approvals/sign/edo, files/search/export/analytics, risk/ppe/incidents/inspections/training.
- Frontend страницы по ключевым доменам и client-portal.

## Что критично по ТЗ
1. Жесткий tenant boundary (`X-Tenant`, scope match, scoped queries).
2. Идемпотентность для mutating endpoint-ов.
3. Неизменяемый аудит на чувствительные операции.
4. Безопасная обработка файлов и webhooks/outbox dedupe.
5. Стабильный pipeline статусов документов.

## Что обнаружено и исправлено в этой задаче
- Исправлен критичный пробел в `assert_tenant_key`: добавлена поддержка legacy-префикса + запрет path traversal.
- Добавлены/обновлены тесты файлового guard.
- Усилен агрегированный sanity-run (`scripts/codex_audit.sh`) критическими наборами тестов tenancy/idempotency/audit/pipeline/webhooks.
- Обновлен контекстный пакет и матрица соответствия.

## Что делать дальше (порядок)
1. Устранить SQLAlchemy relationship overlap warnings в risk-моделях.
2. Расширить e2e role-visibility тесты (admin/client/auditor/specialist).
3. Усилить AV/DLP политику файлового контура на прод уровне.
4. Формализовать backup-restore drill в CI/cron.
5. Синхронизировать оставшиеся legacy docs с фактическим `make codex-audit`.

## Команды
- Локальный старт: `make cs:dev`
- Базовые тесты: `make cs:test`
- Критический sanity: `make codex-audit`
- Финальная приемка: `make final-acceptance`

## Что проверять в первую очередь
1. `make codex-audit`
2. `tests/test_tenant_security.py`, `tests/test_idempotency.py`, `tests/test_documents_status_flow.py`
3. `backend/tests/test_next42_rbac_abac_audit.py`, `backend/tests/test_files_module_basics.py`
