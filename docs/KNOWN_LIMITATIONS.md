# KNOWN_LIMITATIONS

## Приемлемо для пилота
- Есть предупреждения SQLAlchemy (relationship overlaps) без падения функционала; требуют cleanup.
- Часть интеграций EDO/подписания работает через mock/provider-stub режим.
- PWA/offline синхронизация реализована частично (без полной parity сложных сценариев).

## Неприемлемо для промышленной эксплуатации
- Нет полностью автоматизированного backup/restore drill с регулярной валидацией.
- Не завершен full hardening антивирусной/контентной проверки файлов на уровне enterprise политики.
- Не закрыт весь объем e2e permission-matrix (admin/client/auditor/specialist) для UI + API в едином прогоне.
