from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_activity_type_schema_bounds():
    from app.schemas.medical import PsychiatricActivityTypeCreate

    ok = PsychiatricActivityTypeCreate(code="height", name="Высота")
    assert ok.interval_days == 1825  # 5y default
    with pytest.raises(ValidationError):
        PsychiatricActivityTypeCreate(code="", name="x")  # empty code
    with pytest.raises(ValidationError):
        PsychiatricActivityTypeCreate(code="h", name="x", interval_days=0)  # < 1


def test_exam_schema_carries_psychiatric_fields():
    from datetime import date

    from app.models.models import MedicalExamKind
    from app.schemas.medical import MedicalExamCreate, MedicalExamRead

    c = MedicalExamCreate(
        person_id="p1",
        exam_kind=MedicalExamKind.PSYCHIATRIC,
        exam_date=date(2026, 1, 1),
        psychiatric_protocol_no="ПРО-1",
        psychiatric_activity_codes=["height"],
    )
    assert c.psychiatric_activity_codes == ["height"]
    # Read defaults are safe for non-psychiatric records
    assert "psychiatric_protocol_no" in MedicalExamRead.model_fields
    assert "psychiatric_activity_codes" in MedicalExamRead.model_fields


def test_position_activities_in_schema():
    from app.schemas.medical import PositionActivitiesIn

    body = PositionActivitiesIn(activity_codes=["height", "transport"])
    assert body.activity_codes == ["height", "transport"]
    assert PositionActivitiesIn().activity_codes == []
