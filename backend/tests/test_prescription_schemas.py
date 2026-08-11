"""Prescription schema contract for the lifecycle (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.models import PrescriptionStatus
from app.schemas.prescriptions import (
    PrescriptionCreate,
    PrescriptionRead,
    PrescriptionTransition,
    PrescriptionUpdate,
)


def test_create_has_no_status_field() -> None:
    assert "status" not in PrescriptionCreate.model_fields


def test_update_has_no_status_field() -> None:
    assert "status" not in PrescriptionUpdate.model_fields


def test_read_exposes_evidence_and_closed_at() -> None:
    fields = PrescriptionRead.model_fields
    assert "evidence" in fields
    assert "closed_at" in fields


def test_transition_defaults_and_target() -> None:
    t = PrescriptionTransition(to=PrescriptionStatus.IN_PROGRESS)
    assert t.to == PrescriptionStatus.IN_PROGRESS
    assert t.evidence is None
    assert t.note is None


def test_transition_requires_target() -> None:
    with pytest.raises(ValidationError):
        PrescriptionTransition()
