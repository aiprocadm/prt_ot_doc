"""Registration/wiring tests for the prescriptions escalation beat task. App-free."""

from __future__ import annotations

from app.services.celery_app import celery_app
from app.tasks import _core  # noqa: F401  -- importing registers @celery_app.task decorators


def test_beat_schedule_registers_daily_escalation() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "prescriptions-escalate-daily" in schedule
    entry = schedule["prescriptions-escalate-daily"]
    assert entry["task"] == "prescriptions.escalate.tick"
    # crontab(hour=2, minute=0) -> .hour and .minute are sets of ints
    assert 2 in entry["schedule"].hour
    assert 0 in entry["schedule"].minute


def test_escalation_task_is_registered() -> None:
    assert "prescriptions.escalate.tick" in celery_app.tasks
