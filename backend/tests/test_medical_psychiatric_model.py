"""ORM models for 342н psychiatric assessment exist and persist."""

from __future__ import annotations


def test_psychiatric_models_and_exam_columns_importable():
    from app.models.models import (
        MedicalExam,
        PsychiatricActivityType,
        PsychiatricPositionActivity,
    )

    # tables registered under canonical names
    assert PsychiatricActivityType.__tablename__ == "psychiatric_activity_type"
    assert PsychiatricPositionActivity.__tablename__ == "psychiatric_position_activity"
    # additive exam columns present
    cols = set(MedicalExam.__table__.columns.keys())
    assert {"psychiatric_protocol_no", "psychiatric_activity_codes"} <= cols
    # catalog defaults 5y periodicity
    assert PsychiatricActivityType.__table__.c.interval_days.default.arg == 1825

    # unique constraint on the activity-type catalog (tenant-scoped by code)
    at_uniques = {
        tuple(c.name for c in con.columns)
        for con in PsychiatricActivityType.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("tenant_id", "code") in at_uniques

    # mapping table columns + composite unique constraint
    pa_cols = set(PsychiatricPositionActivity.__table__.columns.keys())
    assert {"position_id", "activity_code"} <= pa_cols
    pa_uniques = {
        tuple(c.name for c in con.columns)
        for con in PsychiatricPositionActivity.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("tenant_id", "position_id", "activity_code") in pa_uniques
