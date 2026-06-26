"""Read-projection + mapping helpers for СОУТ срез-1 (P10-04).

Kept DB-agnostic where possible: ``workplace_to_read`` / ``build_report`` take
already-loaded ORM rows (or SimpleNamespace in tests) so the reassessment-due
projection and report grouping are unit-testable without a session.
"""
from __future__ import annotations

from datetime import date

from app.domains.sout.lifecycle import is_reassessment_due
from app.schemas.sout import (
    CampaignReport,
    CampaignRead,
    FactorRead,
    GuaranteeRead,
    WorkplaceReport,
    WorkplaceRead,
)


def _today() -> date:
    return date.today()


def workplace_to_read(workplace, *, today: date | None = None) -> WorkplaceRead:
    today = today or _today()
    return WorkplaceRead(
        id=workplace.id,
        campaign_id=workplace.campaign_id,
        workplace_code=workplace.workplace_code,
        position_name=workplace.position_name,
        person_id=workplace.person_id,
        assessed_class=workplace.assessed_class,
        assessment_date=workplace.assessment_date,
        next_assessment_date=workplace.next_assessment_date,
        is_reassessment_due=is_reassessment_due(workplace.next_assessment_date, today),
        created_at=workplace.created_at,
        updated_at=workplace.updated_at,
    )


def build_report(campaign, workplaces_with_children, *, today: date | None = None) -> CampaignReport:
    """workplaces_with_children: iterable of ``(workplace_row, [factor_rows], [guarantee_rows])``."""
    today = today or _today()
    grouped = [
        WorkplaceReport(
            workplace=workplace_to_read(workplace, today=today),
            factors=[FactorRead.model_validate(f, from_attributes=True) for f in factors],
            guarantees=[GuaranteeRead.model_validate(g, from_attributes=True) for g in guarantees],
        )
        for workplace, factors, guarantees in workplaces_with_children
    ]
    return CampaignReport(
        campaign=CampaignRead.model_validate(campaign, from_attributes=True),
        workplaces=grouped,
    )
