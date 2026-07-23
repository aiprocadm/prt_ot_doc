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
