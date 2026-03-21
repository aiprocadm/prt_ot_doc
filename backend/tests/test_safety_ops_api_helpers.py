from __future__ import annotations

from datetime import date, datetime, timezone

from app.api.routes.safety_ops import _serialize_action, _serialize_finding
from app.models.safety_ops import CorrectiveAction, Finding


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
