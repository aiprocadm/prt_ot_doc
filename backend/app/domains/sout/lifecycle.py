"""Pure-function lifecycle rules for СОУТ срез-1.

No DB access — callers pass current/target states. Mirrors the
committees/work_permits lifecycle style (raise a typed error; route maps to 409).
"""

from __future__ import annotations

from datetime import date

from app.models.sout import SoutCampaignStatus, SoutClass

#: Severity ranking of the class of working conditions (ФЗ-426 ст. 14):
#: optimal(1) < acceptable(2) < harmful 3.1–3.4 < dangerous(4). Higher = worse.
CLASS_SEVERITY: dict[SoutClass, int] = {
    SoutClass.OPTIMAL: 1,
    SoutClass.ACCEPTABLE: 2,
    SoutClass.HARMFUL_3_1: 3,
    SoutClass.HARMFUL_3_2: 4,
    SoutClass.HARMFUL_3_3: 5,
    SoutClass.HARMFUL_3_4: 6,
    SoutClass.DANGEROUS: 7,
}

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


def validate_campaign_transition(current: SoutCampaignStatus, target: SoutCampaignStatus) -> None:
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


def is_class_worsening(old: SoutClass | None, new: SoutClass | None) -> bool:
    """True when the new class is more severe than the old one.

    First assessment (``old is None``) is never "worsening" — there is no prior
    baseline to deteriorate from. An unknown new class also counts as not-worse.
    """
    if old is None or new is None:
        return False
    return CLASS_SEVERITY[new] > CLASS_SEVERITY[old]
