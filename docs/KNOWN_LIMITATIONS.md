# KNOWN_LIMITATIONS

## Приемлемо для пилотного запуска
1. Частичные SAWarning в ORM-моделях risk/workplace/position (после текущих фиксов их меньше, но cleanup не завершен).
2. Часть EDO/sign-интеграций работает в mock/stub режиме.
3. Offline/PWA реализован без полной parity для сложных конфликтных сценариев.

## Неприемлемо для промышленной эксплуатации
1. Нет полностью автоматизированного регулярного backup/restore drill с обязательной валидацией после восстановления.
2. Нет завершенного enterprise hardening для файлового контура (политики AV/DLP/retention/governance в полном объеме).
3. Неполная сквозная e2e матрица прав (frontend+api) для всех ролей (admin/client/auditor/specialist).

- (Обновление) Ранее обнаруженный разрыв tenant-контекста для inbound webhook задач устранен; сохраняются общие ограничения по legacy предупреждениям ORM/SQLAlchemy.

- (Обновление) Критичный public-prefix bypass в tenant middleware закрыт; маршруты вида `/api/v1/publicity` больше не обходят tenant guard.
- Устранено в этой итерации: bypass tenant guard через суффикс `openapi.json` (неактуально после фикса middleware и регрессионного теста).
- Устранено в этой итерации: риск слишком длинного TTL для presigned download URL — введены границы `60..3600` на уровне конфигурации.


- (Обновление) Ранее критичный пробел RBAC на части маршрутов `client-portal-v1` устранен; ограничения перенесены в раздел e2e-покрытия UI-guards (см. FINAL_CRITICAL_GAPS).

## RC hardening notes
- Structured API errors are now normalized for critical acceptance paths, but some legacy endpoints still rely on compatibility aliases (`trace_id`, `request_id`) alongside the RC contract fields.
- Lightweight perf tooling exists for pilot/stage smoke (`scripts/perf/api_load.py`), but sustained queue saturation and long-running document/PDF throughput should still be validated on target infrastructure.
- CRM-to-billing end-to-end UI acceptance is narrower than API coverage and should remain part of the pilot UAT script.
