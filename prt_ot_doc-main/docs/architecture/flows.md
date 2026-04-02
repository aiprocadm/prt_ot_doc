# Сквозные потоки и согласование слоёв

Документ описывает ключевые end-to-end потоки и соответствие между UI, API, pipeline, outbox и событиями.

## Документы (генерация и экспорт)
**UI:** мастер документов → запрос генерации → отслеживание статуса.

**API:**
- `POST /documents/generate` (Idempotency-Key обязателен).
- `GET /documents/tasks/{task_id}` (статус pipeline).
- `GET /documents/{id}` / `GET /documents` (реестр).

**Pipeline / Outbox:**
- Выполняется pipeline, результаты фиксируются в `pipeline_runs`.
- При завершении формируется событие `DocumentGenerated` или `DocumentFailed`.

**UI реакция:**
- Polling статуса до финального состояния.
- Ошибки отображаются человеку через `error_code` и `last_error`.

## Обязательства и задачи
**UI:** реестр задач → фильтры по типу, сроку, приоритету.

**API:**
- `GET /tasks` с фильтрами `type`, `overdue`, `priority`.
- `GET /obligations/summary` для подсчётов по видам источников.

**Outbox:**
- `TaskDueSoon` / `TaskOverdue` как события напоминаний.

**UI реакция:**
- Просрочки подсвечиваются (SLA).

## Риски и мероприятия
**UI:** оценка риска → карточка риска → план мероприятий.

**API:**
- `POST /risk/assess`.
- `GET /risk/action-plans`.
- `GET /tasks?type=risk_action`.

**Outbox:**
- `RiskAssessed` для внешней интеграции.

## Управленческий дашборд
**UI:** сводка KPI → переход в реестры.

**API:**
- `GET /dashboard/summary`.

**Поля:**
- `overdue_tasks`, `critical_obligations`.
- `incidents_open`, `risks_total`.
- `training.{total,overdue,due_soon,status}`.

## События и UX
**UI:** тосты, бейджи, авто-обновление списков.

**API/Outbox:**
- `DocumentGenerated`, `DocumentFailed`, `TaskOverdue`, `RiskAssessed`.

**Примечание:**
- Для ручного воспроизведения событий и диагностики см. `docs/runbook.md`.
