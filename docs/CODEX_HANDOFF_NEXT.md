# CODEX_HANDOFF_NEXT

## 1. Что это за проект
Многопользовательская B2B SaaS-платформа по ОТ/ПБ/ПромБез/экологии с ключевым документным конвейером: шаблон → массовая замена → PDF → согласование/подписание/ЭДО → архив/экспорт.

## 2. Фактическое состояние (по коду)
- Tenant enforcement на уровне middleware + route dependencies для business API.
- RBAC/ABAC, audit log, idempotency, outbox/webhook dedupe реализованы и покрыты тестами.
- Документные эндпоинты `/api/v1/documents/generate` и `/api/v1/documents/batch` активны и используются в тестах.

## 3. Что исправлено в этой задаче
1. **Исправлен критический runtime сбой в документной генерации**: `UnboundLocalError`/`NameError` в `documents` routes (сломанные ветки для `engine_payload` и `payload` в batch flow).
2. **Снижен риск ORM-конфликтов**: добавлены `overlaps` для связей risk/workplace/position/link-моделей (частично сняты SAWarning).
3. **Обновлён операционный контекст**: RUNBOOK/LIMITATIONS/GAPS синхронизированы с фактическим состоянием.

## 4. Что остаётся критичным по ТЗ
1. Жёсткое соблюдение tenant isolation (включая async jobs и file/export/search контуры).
2. Идемпотентность всех mutating API.
3. Иммутабельный аудит для чувствительных операций.
4. Безопасная файловая подсистема (signed URL TTL/access checks/audit download).

## 5. Что делать дальше (рекомендуемый порядок)
1. Завершить cleanup всех SAWarning по risk relationships (добавить оставшиеся `overlaps`/`back_populates` + тест с warning gate).
2. Дожать e2e-матрицу ролей для frontend (admin/client/auditor/specialist).
3. Формализовать backup/restore drill как обязательный периодический прогон.
4. Усилить enterprise-политику для файлового контура (AV/DLP/retention/audit).

## 6. Ключевые команды
- `make cs:dev` — локальный старт.
- `make codex-audit` — критический sanity срез.
- `pytest -q tests/test_documents_generate.py tests/test_template_delete.py tests/integration/test_idempotency_generate.py tests/test_tenant_header_required.py` — быстрый регресс document+tenancy+idempotency.

## 7. Что проверять в первую очередь при следующем заходе
1. `make codex-audit`.
2. Документные сценарии генерации/батча.
3. Tenant boundary + idempotency mismatch сценарии.
