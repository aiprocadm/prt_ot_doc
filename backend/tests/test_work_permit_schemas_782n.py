import pytest
from pydantic import ValidationError

from app.schemas.work_permit import WorkPermitCreate


def test_create_accepts_782n_fields():
    payload = WorkPermitCreate(
        work_type="height", zone_text="фасад, ось 3-5",
        subdivision_text="Цех №2", content_text="монтаж ограждения",
        conditions_text="высота 8 м", safety_systems=["fall_arrest", "rescue_evacuation"],
        measures_before_text="установить ограждение", measures_during_text="контроль привязи",
        special_conditions_text="ветер до 10 м/с", ppe_text="каска, привязь",
    )
    assert payload.safety_systems == ["fall_arrest", "rescue_evacuation"]
    assert payload.subdivision_text == "Цех №2"


def test_create_rejects_unknown_safety_system():
    with pytest.raises(ValidationError):
        WorkPermitCreate(work_type="height", zone_text="z", safety_systems=["bogus"])
