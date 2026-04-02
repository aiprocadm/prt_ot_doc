from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes.safety_ops import _audit_event, _serialize_action, _serialize_finding
from app.models.safety_ops import CorrectiveAction, Finding
from app.services.audit import AuditService


def test_serialize_finding_exposes_operational_projection_fields() -> None:
    row = Finding(
        id="finding-1",
        tenant_id="tenant-1",
        source_type="inspection",
        source_id="insp-1",
        title="Нет ограждения",
        description="Опасная зона без барьера",
        severity="critical",
        status="open",
        finding_type="nonconformity",
        due_date=date(2026, 4, 15),
        site_id="site-1",
        created_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )

    payload = _serialize_finding(row)

    assert payload["severity"] == "critical"
    assert payload["source_type"] == "inspection"
    assert payload["due_date"] == "2026-04-15"
    assert payload["created_at"].startswith("2026-03-21T")



def test_serialize_action_marks_overdue_and_keeps_effectiveness() -> None:
    row = CorrectiveAction(
        id="action-1",
        tenant_id="tenant-1",
        source_type="finding",
        source_id="finding-1",
        title="Установить ограждение",
        action_type="corrective",
        status="open",
        due_date=date(2026, 3, 20),
        effectiveness_status="partial",
        responsible_user_id="user-1",
        completed_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )

    payload = _serialize_action(row)

    assert payload["status"] == "overdue"
    assert payload["effectiveness_status"] == "partial"
    assert payload["responsible_user_id"] == "user-1"
    assert payload["completed_at"].startswith("2026-03-21T")


@pytest.mark.asyncio
async def test_audit_event_forwards_trace_and_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_log_event(self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(AuditService, "log_event", _fake_log_event)

    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-123"),
        headers={"user-agent": "pytest-agent"},
    )

    await _audit_event(
        request=request,
        session=AsyncMock(),
        tenant_id="tenant-1",
        action="create",
        object_type="finding",
        object_id="finding-1",
        user_id="user-1",
        details={"severity": "high"},
    )

    assert captured["request_id"] == "trace-123"
    assert captured["user_agent"] == "pytest-agent"
    assert captured["ip"] == "127.0.0.1"
