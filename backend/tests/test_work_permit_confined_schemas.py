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


def test_create_accepts_valid_hot_work_type_specific():
    m = WorkPermitCreate(
        work_type="hot_work",
        zone_text="эстакада №3",
        type_specific={
            "fire_fighting_means": ["extinguisher_powder", "sand"],
            "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
        },
    )
    assert m.type_specific["fire_fighting_means"] == ["extinguisher_powder", "sand"]


def test_create_rejects_bad_fire_fighting_means():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="hot_work", zone_text="эстакада",
            type_specific={"fire_fighting_means": ["laser"]},
        )


def test_create_rejects_ventilation_on_hot_work():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="hot_work", zone_text="эстакада",
            type_specific={"ventilation": "forced"},
        )
