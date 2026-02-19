# Verticals Gap Report (NEXT-2)

Аудит выполнен по `backend/app/api/routes/*`, `backend/app/services/*`, `backend/app/domains/*`, `backend/app/models/*`, `frontend/src/pages/*`, `frontend/src/features/*`, `tests/*`.

| Модуль | Есть модели? | Есть сервис/домен? | Есть роуты API? | Есть UI? | Есть события (outbox) | Есть тесты? | Статус | Файлы/заметки |
|---|---|---|---|---|---|---|---|---|
| Risks | ✅ | ✅ | ✅ | ✅ | ✅ (`RiskAssessed`) | ✅ | OK | `backend/app/api/routes/risk.py`, `backend/app/domains/risk/*`, `frontend/src/pages/risk/RiskPage.tsx`, `tests/test_risk_engine.py` |
| PPE | ✅ | ✅ | ✅ | ✅ | ✅ (`PPEIssued`) | ✅ | OK | `backend/app/api/routes/ppe.py`, `backend/app/domains/ppe/service.py`, `frontend/src/pages/ppe/PpePage.tsx`, `tests/api/test_ppe_events.py` |
| Training | ✅ | ✅ | ✅ | ✅ | ✅ (`TrainingCompleted`) | ✅ | OK | `backend/app/api/routes/training.py`, `backend/app/domains/training/service.py`, `frontend/src/pages/training/TrainingPage.tsx`, `tests/api/test_training_api.py` |
| Briefings | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Missing | Отдельного журнала `briefings` и action API нет (вне текущего объёма, TODO) |
| Incidents | ✅ | ✅ | ✅ | ✅ | ❌ (явный outbox event отсутствует) | ✅ | Partial | `backend/app/api/routes/incidents.py`, `backend/app/domains/incidents/service.py`, `frontend/src/pages/incidents/IncidentsPage.tsx`, `tests/api/test_incidents_api.py` |
| Inspections/Prescriptions | ✅ | ✅ | ✅ | ✅ | ❌ (явный outbox event отсутствует) | ✅ | Partial | `backend/app/api/routes/inspections.py`, `backend/app/api/routes/prescriptions.py`, `frontend/src/pages/inspections/InspectionsPage.tsx`, `tests/api/test_inspections_api.py` |
| Obligations | ✅ (`Task`) | ✅ | Partial | Partial | n/a | ✅ | Partial | Был только summary endpoint; добавлены list/close (`/obligations`, `PATCH /obligations/{id}`), отдельной страницы `/obligations` пока нет |
| Reports/KPI | Partial | Partial | Partial | Missing | n/a | Partial | Partial | Добавлен `GET /reports/kpi` + UI `/reports`; расширение KPI возможно |

## Резюме

1. Основные вертикали Risks/PPE/Training присутствуют end-to-end.
2. Incidents/Inspections работают как MVP по CRUD и audit, но без outbox-событий уровня `IncidentCreated/InspectionCreated`.
3. Обязательства и отчёты доведены до MVP через новые endpoint'ы и экран отчётов.
4. Журнал инструктажей (`briefings`) остаётся отдельным TODO.
