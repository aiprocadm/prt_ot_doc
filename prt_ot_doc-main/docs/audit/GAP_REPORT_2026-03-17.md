# GAP Report (targeted increment)

## Что найдено
- В outbox-контуре отсутствовали явные доменные события создания инцидента и проверки (`IncidentCreated`, `InspectionCreated`).
- В `TZ_COVERAGE_MATRIX.md` блок TZ-9.3 оставался в `Partial` с планом на будущее.

## Что исправлено
- Добавлены типы событий и payload-нормализация для `IncidentCreated` и `InspectionCreated`.
- Эмиссия событий включена в critical create-flow:
  - `POST /incidents`
  - `POST /inspections`
- Для создания инцидента добавлен audit-event в create-path.
- Добавлены unit-тесты на нормализацию payload и dedupe key для новых событий.
- Обновлена матрица покрытия TZ (TZ-9.1/TZ-9.2/TZ-9.3).

## Что оставлено в P2/backlog
- Outbox-событие по просрочке предписаний (`PrescriptionOverdue`) и связанным corrective-flow.
- Более глубокая контрактная интеграция (end-to-end API tests с проверкой outbox delivery history по incident/inspection).
- P0/P1 блоки вне данного инкремента: briefings end-to-end, package pipeline depth, replace persisted patch storage, PDF hardening.
