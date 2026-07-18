# DEMO WALKTHROUGH 2 — Verticals MVP

## 1) Старт окружения
1. `make cs:reset`
2. `cp .env.example .env`
3. В `.env` включить `DEMO_BOOTSTRAP=1`
4. `make cs:dev`

## 2) Логин и контекст
1. Открыть UI, войти под demo/admin.
2. Убедиться, что выбран нужный tenant (header `X-Tenant`).

## 3) Risks: assess risk
1. Перейти в **Риски** (`/risk`).
2. Заполнить форму оценки, выбрать hazards, сохранить.
3. Проверить, что новая оценка появилась в таблице.
4. Проверить событие в outbox-admin: `RiskAssessed`.

## 4) PPE: issue
1. Перейти в **СИЗ и склады** (`/ppe`).
2. Создать номенклатуру СИЗ (если пусто), затем выполнить выдачу сотруднику.
3. Открыть журнал выдач и убедиться, что запись создана.
4. Проверить outbox событие `PPEIssued`.

## 5) Training: enroll + complete
1. Перейти в **Обучение и инструктажи** (`/training`).
2. Создать/назначить план обучения.
3. Создать сессию со статусом completed (MVP-вариант завершения).
4. Проверить outbox событие `TrainingCompleted`.

## 6) Incidents + corrective action / prescriptions + obligations
1. Перейти в **Инциденты/НС** (`/incidents`) и зарегистрировать инцидент.
2. Перейти в **Проверки/предписания** (`/inspections`) и создать проверку.
3. Добавить предписание с `due_at` в прошлом (для демо просрочки).
4. Проверить `/api/v1/obligations?overdue=true` — должна быть просроченная задача.
5. Закрыть обязательство через `PATCH /api/v1/obligations/{id}`.

## 7) Reports / Dashboard
1. Открыть **Отчёты** (`/reports`) — убедиться, что KPI загружаются.
2. Открыть **Главная** (`/dashboard`) — проверить сводные карточки.

## 8) Тесты
- `make cs:test`
- `npm --prefix frontend test`
