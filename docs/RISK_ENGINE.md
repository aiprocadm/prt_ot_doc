# RISK_ENGINE

## Scope and canonical code paths
Risk functionality is implemented as a **tenant-aware domain foundation** with calculation and enterprise APIs distributed across:

- `backend/app/api/routes/risk.py`
- `backend/app/api/routes/risk_enterprise.py`
- `backend/app/domains/risk/calc.py`
- `backend/app/modules/risk/services.py`
- `backend/app/models/risk.py`
- `backend/app/migrations/versions/20250320_risk_assessment_action_plan.py`
- `backend/app/migrations/versions/20250322_risk_cards_action_plans.py`
- `backend/app/migrations/versions/20260318_next67_risk_custom_enum_hotfix.py`

## Current engine posture
- probability × severity and tenant-specific methodology groundwork exist;
- risk cards / action plans / assessment records already have persistence and migration support;
- enterprise routes are separate from simpler risk routes to preserve backward compatibility while the model evolves;
- downstream incidents, prescriptions, and corrective actions influence the broader risk context via related safety-core modules.

## Hardening notes for this wave
- The repository documentation now explicitly marks risk as a **partial but coherent** engine rather than overstating completeness.
- Acceptance, architecture, and gap documents now point to incidents/inspections/prescriptions as the correct adjacent modules for residual-risk and overdue-measure flows.

## Remaining gaps
- Fine-Kinney and richer tenant-defined methodologies need broader acceptance coverage before being considered production-complete.
- Residual risk recalculation and full NPA-driven impact propagation exist as design foundations but are not yet documented as universally automated.
- BI-ready analytics for risk trend rollups should rely on read models/projections rather than direct registry queries as the next hardening step.
