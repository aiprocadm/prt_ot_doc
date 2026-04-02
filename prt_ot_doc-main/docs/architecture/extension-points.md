# Extension Points

## Новые модули
1. Добавьте модели в `backend/app/models`.
2. Создайте маршруты в `backend/app/api/routes` и зарегистрируйте их в `api/v1/router.py`.
3. Вынесите бизнес-логику в `backend/app/services`.

## Новые события (Outbox)
1. Добавьте тип события в `backend/app/services/events.py`.
2. Добавьте нормализацию payload и правила дедупликации.
3. Укажите подписки в таблице `webhooksubscription` или через админ API.
4. Проверьте, что `OutboxService.enqueue` получает корректный `event_type`.

## Новые обязательства/напоминания
1. Добавьте обработчики в `backend/app/services/obligations.py`.
2. Проверьте расписание `tasks.reminders.dispatch` (Celery beat).
3. Для доставки используйте outbox с событиями `TaskDueSoon`/`TaskOverdue`.

## Новые лимиты/ограничения
1. Добавьте переменные в `Settings` (`backend/app/core/config.py`).
2. Примените проверки в API/сервисах и добавьте тесты.
