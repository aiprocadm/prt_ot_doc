# FINAL_CRITICAL_GAPS

## Blocker
1. **`packs/run` idempotency нестабильность**
   - Почему важно: может ломать повторяемость и надежность batch generation.
   - Что делать: отладить traceback в `POST /api/v1/packs/run`, стабилизировать обработку enqueue/fallback path, добавить regression-тесты на duplicate key + payload mismatch.

## Critical
1. **Неполная ABAC/RBAC matrix coverage**
   - Почему важно: риск утечки/неавторизованного доступа через редкие роли.
   - Что делать: добавить табличный набор тестов по ролям (admin/client_admin/client_user/auditor/specialist).

2. **Search/Export leakage coverage недостаточно жёсткое**
   - Почему важно: в multi-tenant SaaS это критично для data isolation.
   - Что делать: добавить интеграционные tenant-A vs tenant-B тесты на search/export endpoints.

3. **File security edge cases покрыты частично**
   - Почему важно: signed URL / download scope / upload validation напрямую связаны с безопасностью данных.
   - Что делать: расширить negative tests на истёкшие URL и tenant mismatch download.

## Major
1. **Observability/Backup/Restore**
   - Почему важно: готовность к pilot/prod инцидентам.
   - Что делать: оформить и автоматизировать проверки backup/restore + readiness SLO.
