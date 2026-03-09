# FIRST_RUN_ONBOARDING

Состояние onboarding хранится в `Tenant.settings.bootstrap_state`:
- `configured`
- `remaining_actions`

Минимальный first-run flow:
1. Профиль компании
2. Объекты
3. Пользователи/роли
4. Импорт сотрудников
5. Шаблоны и пресеты
6. Обучение/СИЗ/риски
7. Интеграции (опционально)
8. Тестовая генерация/экспорт/аппрув

Шаги допускают skip/resume.
