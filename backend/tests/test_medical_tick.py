"""Smoke tests for the medical.contingent.tick Celery beat task."""

from __future__ import annotations

from app.services.celery_app import celery_app
from app.tasks import _core  # noqa: F401  -- importing registers @celery_app.task decorators


def test_beat_schedule_registers_medical_contingent_daily() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "medical-contingent-daily" in schedule
    entry = schedule["medical-contingent-daily"]
    assert entry["task"] == "medical.contingent.tick"
    # crontab(hour=3, minute=0) -> .hour and .minute are sets of ints
    assert 3 in entry["schedule"].hour
    assert 0 in entry["schedule"].minute


def test_medical_contingent_tick_task_is_registered() -> None:
    assert "medical.contingent.tick" in celery_app.tasks
