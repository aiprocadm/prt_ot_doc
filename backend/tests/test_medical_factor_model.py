"""Model-shape guards for the 29н factor catalog (§9.2)."""

from app.models.models import MedicalFactor
from app.models.risk import RiskHazard


def test_medical_factor_table_and_columns():
    cols = MedicalFactor.__table__.columns
    assert MedicalFactor.__tablename__ == "medical_factor"
    for name in (
        "id",
        "tenant_id",
        "code",
        "name",
        "category",
        "exam_kinds",
        "periodicity_months",
        "participants",
        "lab_tests",
    ):
        assert name in cols, f"missing column {name}"
    uniques = {
        tuple(c.name for c in con.columns)
        for con in MedicalFactor.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("tenant_id", "code") in uniques


def test_risk_hazard_has_medical_factor_code():
    assert "medical_factor_code" in RiskHazard.__table__.columns
