"""Pin: prescription lifecycle model fields (TZ-3.4-V12-01)."""

from __future__ import annotations


def test_prescription_status_has_verified() -> None:
    from app.models.models import PrescriptionStatus

    assert PrescriptionStatus.VERIFIED.value == "verified"


def test_prescription_has_lifecycle_columns() -> None:
    from app.models.models import Prescription

    cols = Prescription.__table__.c
    assert "evidence" in cols
    assert "closed_at" in cols
    assert cols["evidence"].nullable is True
    assert cols["closed_at"].nullable is True
