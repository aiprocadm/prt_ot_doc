"""Unit: СОУТ schemas round-trip + reassessment projection (P10-04)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.sout import SoutCampaignStatus, SoutClass, SoutGuaranteeKind
from app.schemas.sout import (
    CampaignCreate,
    CampaignStatusUpdate,
    FactorCreate,
    FactorUpdate,
    GuaranteeCreate,
    MedicalExamSuggestion,
    NormSuggestions,
    PpeNormSuggestion,
    WorkplaceCreate,
    WorkplaceRead,
    WorkplaceUpdate,
)


def test_campaign_create_defaults():
    c = CampaignCreate(name="СОУТ 2026")
    assert c.expert_org_name is None
    assert c.report_date is None
    assert c.planned_date is None


def test_campaign_status_update_enum():
    u = CampaignStatusUpdate(status=SoutCampaignStatus.IN_PROGRESS)
    assert u.status is SoutCampaignStatus.IN_PROGRESS


def test_workplace_create_optional_class():
    w = WorkplaceCreate(workplace_code="РМ-001", position_name="Сварщик")
    assert w.assessed_class is None
    assert w.person_id is None


def test_workplace_read_carries_reassessment_flag():
    w = WorkplaceRead(
        id="w1",
        campaign_id="c1",
        workplace_code="РМ-001",
        position_name="Сварщик",
        person_id=None,
        assessed_class=SoutClass.DANGEROUS,
        assessment_date=date(2026, 1, 1),
        next_assessment_date=date(2026, 6, 1),
        is_reassessment_due=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert w.is_reassessment_due is True
    assert w.assessed_class is SoutClass.DANGEROUS


def test_workplace_update_partial():
    u = WorkplaceUpdate(assessed_class=SoutClass.OPTIMAL)
    assert u.position_name is None


def test_factor_and_guarantee_create():
    f = FactorCreate(name="Шум")
    assert f.measured_class is None
    g = GuaranteeCreate(kind=SoutGuaranteeKind.MILK)
    assert g.detail is None


def test_workplace_create_accepts_position_id() -> None:
    wp = WorkplaceCreate(workplace_code="РМ-1", position_name="Сварщик", position_id="pos-1")
    assert wp.position_id == "pos-1"


def test_factor_update_accepts_hazard_id() -> None:
    fu = FactorUpdate(hazard_id="haz-1")
    assert fu.model_dump(exclude_unset=True) == {"hazard_id": "haz-1"}


def test_norm_suggestions_envelope() -> None:
    ppe = PpeNormSuggestion(
        position_id="pos-1",
        hazard_id="haz-1",
        hazard_title="Шум",
        factor_name="Шум",
        factor_code="4.50",
        measured_class=SoutClass.HARMFUL_3_1,
        reason="demo",
    )
    med = MedicalExamSuggestion(
        position_id="pos-1",
        exam_kind="periodic",
        periodicity_months=12,
        factor_codes=["4.4"],
        reason="demo",
    )
    env = NormSuggestions(ppe=[ppe], medical=[med])
    assert env.ppe[0].hazard_id == "haz-1"
    assert env.medical[0].exam_kind == "periodic"
