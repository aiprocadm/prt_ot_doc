"""Pure-function lifecycle rules for СОУТ срез-1.

No DB access — callers pass current/target states. Mirrors the
committees/work_permits lifecycle style (raise a typed error; route maps to 409).
"""
from __future__ import annotations

from datetime import date

from app.models.sout import SoutCampaignStatus

#: Allowed campaign status transitions.
_ALLOWED: dict[SoutCampaignStatus, set[SoutCampaignStatus]] = {
    SoutCampaignStatus.PLANNED: {SoutCampaignStatus.IN_PROGRESS, SoutCampaignStatus.CANCELLED},
    SoutCampaignStatus.IN_PROGRESS: {SoutCampaignStatus.COMPLETED, SoutCampaignStatus.CANCELLED},
    SoutCampaignStatus.COMPLETED: {SoutCampaignStatus.DECLARED},
    SoutCampaignStatus.DECLARED: set(),
    SoutCampaignStatus.CANCELLED: set(),
}

#: Statuses where the campaign roster is still editable (workplaces/factors).
_OPEN_STATUSES = {SoutCampaignStatus.PLANNED, SoutCampaignStatus.IN_PROGRESS}


class CampaignTransitionError(ValueError):
    """Raised on an illegal campaign transition or edit of a closed campaign."""


def validate_campaign_transition(
    current: SoutCampaignStatus, target: SoutCampaignStatus
) -> None:
    if target not in _ALLOWED.get(current, set()):
        raise CampaignTransitionError(
            f"Cannot transition campaign {current.value} -> {target.value}"
        )


def ensure_campaign_open(status: SoutCampaignStatus) -> None:
    """Workplaces/factors/guarantees may only be added while the campaign is open."""
    if status not in _OPEN_STATUSES:
        raise CampaignTransitionError(
            f"Campaign roster is editable only while planned/in_progress (status={status.value})"
        )


def is_reassessment_due(next_assessment_date: date | None, today: date) -> bool:
    """A workplace needs re-assessment when its next date has reached/passed today."""
    if next_assessment_date is None:
        return False
    return next_assessment_date <= today
