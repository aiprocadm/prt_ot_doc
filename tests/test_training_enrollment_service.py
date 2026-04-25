from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.modules.training.services as training_services
from app.modules.training.services import TrainingEnrollmentService


class _FakeAttempt:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@pytest.mark.asyncio
async def test_submit_attempt_marks_passed_and_computes_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(training_services, "TrainingAttempt", _FakeAttempt)
    session = AsyncMock()
    session.add = MagicMock()
    service = TrainingEnrollmentService()

    enrollment = SimpleNamespace(
        id="enr-1",
        tenant_id="tenant-1",
        training_program_id="prog-1",
        started_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        attempt_count=0,
        status="assigned",
        score=None,
        completed_at=None,
        expires_at=None,
    )
    test = SimpleNamespace(passing_score=70, attempts_limit=2)
    program = SimpleNamespace(validity_months=12, tenant_id="tenant-1")

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = test
    session.execute.return_value = execute_result
    session.get.return_value = program

    attempt = await service.submit_attempt(session, enrollment, {"score": 80})

    assert enrollment.status == "passed"
    assert enrollment.completed_at is not None
    assert enrollment.expires_at is not None
    assert enrollment.expires_at.year == enrollment.completed_at.year + 1
    assert enrollment.attempt_count == 1
    assert attempt.passed is True


@pytest.mark.asyncio
async def test_submit_attempt_enforces_attempt_limit() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    service = TrainingEnrollmentService()

    enrollment = SimpleNamespace(
        id="enr-2",
        tenant_id="tenant-1",
        training_program_id="prog-2",
        started_at=datetime.now(tz=timezone.utc),
        attempt_count=2,
        status="in_progress",
        score=None,
        completed_at=None,
        expires_at=None,
    )
    test = SimpleNamespace(passing_score=70, attempts_limit=2)

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = test
    session.execute.return_value = execute_result

    with pytest.raises(ValueError, match="attempts_limit_exceeded"):
        await service.submit_attempt(session, enrollment, {"score": 95})
