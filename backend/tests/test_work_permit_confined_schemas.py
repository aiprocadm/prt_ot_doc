"""Валидация type_specific в схемах наряда-допуска (ОЗП 902н)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.work_permit import WorkPermitCreate


def _base(**extra):
    return {"work_type": "confined_space", "zone_text": "колодец К-12", **extra}


def test_create_accepts_valid_confined_type_specific():
    m = WorkPermitCreate(**_base(type_specific={
        "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
        "ventilation": "forced",
    }))
    assert m.type_specific["ventilation"] == "forced"


def test_create_rejects_bad_parameter():
    with pytest.raises(ValidationError):
        WorkPermitCreate(**_base(type_specific={"gas_analysis": [{"parameter": "xx", "value": "1"}]}))


def test_create_rejects_type_specific_on_height():
    with pytest.raises(ValidationError):
        WorkPermitCreate(work_type="height", zone_text="фасад",
                         type_specific={"ventilation": "forced"})


def test_create_allows_no_type_specific():
    m = WorkPermitCreate(**_base())
    assert m.type_specific is None
