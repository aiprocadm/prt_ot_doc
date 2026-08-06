from __future__ import annotations

from datetime import date

from app.schemas.medical import (
    ContingentItem,
    ContingentPage,
    MedicalExamCreate,
    MedicalExamRead,
    MedicalNormCreate,
    MedicalReferralTransition,
    MedicalSummary,
)


def test_exam_create_requires_core_fields():
    m = MedicalExamCreate(
        person_id="p1", exam_kind="periodic", exam_date=date(2026, 1, 1), fitness="fit"
    )
    assert m.contraindications == []
    assert m.valid_until is None  # optional → service computes


def test_exam_read_has_new_fields():
    fields = set(MedicalExamRead.model_fields)
    assert {
        "exam_kind",
        "fitness",
        "restrictions",
        "contraindications",
        "referral_id",
        "medical_org_name",
    }.issubset(fields)


def test_referral_transition_and_norm_and_contingent():
    MedicalReferralTransition(to="scheduled")
    MedicalNormCreate(position_id="p1", exam_kind="periodic", interval_days=365)
    item = ContingentItem(
        person_id="p1",
        exam_kind="periodic",
        status="missing",
        valid_until=None,
        due_at=date(2026, 1, 1),
    )
    page = ContingentPage(items=[item], total=1)
    assert page.total == 1
    MedicalSummary(by_status={"missing": 1}, total=1, overdue_count=0, suspended_count=0)
