# FEATURE_FLAGS

Pilot flags registry (central):
- edo
- sign
- portal
- pwa
- reports_advanced
- integrations
- billing_enforcement
- demo_data
- advanced_risk_engine
- warehouse
- pdn_subject_rights — права субъекта ПДн (SEC-66, разд. 66.2). **Default-ON**: это
  исполнение требования 152-ФЗ, а не пилот; арендатор отключается явной записью
  `FeatureEnablement(on=False)` → эндпоинты `/privacy/*` отдают 404, журналирование
  доступа к ПДн прекращается.

Требования: per-tenant overrides, env defaults, audit изменений.

## Дисциплины и модули (BIZ-54-57 срез-54, приёмка §58.3)

Пять дисциплин Доп. №1 (`fire_safety`, `industrial_safety`, `ecology`,
`civil_defense`, `road_safety`) и медосмотры (`medical`) — продаваемые модули
(`app/modules/subscription/registry.py`); СИЗ и обучение — ядро. Карточки
объекта 360° и сотрудника 360° показывают статус только по ПРИМЕНИМЫМ
дисциплинам — тем, чей модуль выдан и включён
(`app/services/discipline_applicability.py`). Скрытое названо фразой на самой
карточке («Вне редакции арендатора …»), а не пропущено молча. Другие сводки
(разрез по дисциплинам, центр внимания, отчёты заказчику) пока перечисляют все
восемь — см. handoff среза-54.
