"""Unit: СОУТ schemas round-trip + reassessment projection (P10-04)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.sout import SoutCampaignStatus, SoutClass, SoutGuaranteeKind
from app.schemas.sout import (
    CampaignCreate,
    CampaignStatusUpdate,
    FactorCreate,
    GuaranteeCreate,
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
        id="w1", campaign_id="c1", workplace_code="РМ-001",
        position_name="Сварщик", person_id=None,
        assessed_class=SoutClass.DANGEROUS, assessment_date=date(2026, 1, 1),
        next_assessment_date=date(2026, 6, 1), is_reassessment_due=True,
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
