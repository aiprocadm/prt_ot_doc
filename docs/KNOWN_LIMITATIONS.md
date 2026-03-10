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
