"""Unit: СОУТ lifecycle guards + reassessment-due computation (P10-04)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.sout.lifecycle import (
    CampaignTransitionError,
    ensure_campaign_open,
    is_reassessment_due,
    validate_campaign_transition,
)
from app.models.sout import SoutCampaignStatus

TODAY = date(2026, 6, 26)


def test_planned_to_in_progress_allowed():
    validate_campaign_transition(SoutCampaignStatus.PLANNED, SoutCampaignStatus.IN_PROGRESS)


def test_in_progress_to_completed_allowed():
    validate_campaign_transition(SoutCampaignStatus.IN_PROGRESS, SoutCampaignStatus.COMPLETED)


def test_completed_to_declared_allowed():
    validate_campaign_transition(SoutCampaignStatus.COMPLETED, SoutCampaignStatus.DECLARED)


def test_planned_to_completed_rejected():
    with pytest.raises(CampaignTransitionError):
        validate_campaign_transition(SoutCampaignStatus.PLANNED, SoutCampaignStatus.COMPLETED)


def test_declared_is_terminal():
    with pytest.raises(CampaignTransitionError):
        validate_campaign_transition(SoutCampaignStatus.DECLARED, SoutCampaignStatus.COMPLETED)


def test_cancelled_is_terminal():
    with pytest.raises(CampaignTransitionError):
        validate_campaign_transition(SoutCampaignStatus.CANCELLED, SoutCampaignStatus.IN_PROGRESS)


def test_roster_editable_only_while_open():
    ensure_campaign_open(SoutCampaignStatus.PLANNED)  # no raise
    ensure_campaign_open(SoutCampaignStatus.IN_PROGRESS)  # no raise
    for closed in (
        SoutCampaignStatus.COMPLETED,
        SoutCampaignStatus.DECLARED,
        SoutCampaignStatus.CANCELLED,
    ):
        with pytest.raises(CampaignTransitionError):
            ensure_campaign_open(closed)


def test_reassessment_due_when_date_passed():
    assert is_reassessment_due(TODAY - timedelta(days=1), TODAY) is True


def test_reassessment_due_when_date_today():
    assert is_reassessment_due(TODAY, TODAY) is True


def test_reassessment_not_due_in_future():
    assert is_reassessment_due(TODAY + timedelta(days=1), TODAY) is False


def test_reassessment_not_due_when_no_date():
    assert is_reassessment_due(None, TODAY) is False
