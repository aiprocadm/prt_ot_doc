"""Unit: СОУТ service projection helpers (P10-04)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.domains.sout.service import build_report, workplace_to_read
from app.models.sout import SoutCampaignStatus, SoutClass

TODAY = date(2026, 6, 26)


def _workplace(**kw):
    base = dict(
        id="w1", campaign_id="c1", workplace_code="РМ-001",
        position_name="Электрогазосварщик", person_id=None,
        assessed_class=SoutClass.HARMFUL_3_2, assessment_date=date(2026, 1, 1),
        next_assessment_date=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_workplace_to_read_marks_reassessment_due():
    w = _workplace(next_assessment_date=date(2026, 6, 1))
    read = workplace_to_read(w, today=TODAY)
    assert read.is_reassessment_due is True
    assert read.assessed_class is SoutClass.HARMFUL_3_2


def test_workplace_to_read_not_due_when_future():
    w = _workplace(next_assessment_date=date(2027, 1, 1))
    assert workplace_to_read(w, today=TODAY).is_reassessment_due is False


def test_build_report_groups_factors_and_guarantees():
    campaign = SimpleNamespace(
        id="c1", name="СОУТ 2026", expert_org_name="ООО Эксперт",
        report_number="42", report_date=date(2026, 3, 1),
        status=SoutCampaignStatus.COMPLETED,
        planned_date=None, completed_date=date(2026, 3, 1),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    w = _workplace(next_assessment_date=date(2026, 6, 1))
    factor = SimpleNamespace(
        id="f1", workplace_id="w1", code="4.50", name="Шум",
        measured_class=SoutClass.HARMFUL_3_1, note=None,
    )
    guarantee = SimpleNamespace(
        id="g1", workplace_id="w1", kind="additional_leave", detail="7 дней",
    )
    report = build_report(campaign, [(w, [factor], [guarantee])], today=TODAY)
    assert report.campaign.id == "c1"
    assert len(report.workplaces) == 1
    assert report.workplaces[0].workplace.is_reassessment_due is True
    assert report.workplaces[0].factors[0].name == "Шум"
    assert report.workplaces[0].guarantees[0].detail == "7 дней"
