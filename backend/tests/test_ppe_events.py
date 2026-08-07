"""Payload schemas for the new PPE event types (hermetic)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.events import (
    EventType,
    PPEReplacementDuePayload,
    PPEWrittenOffPayload,
)


def test_event_types_registered():
    assert EventType.PPE_WRITTEN_OFF.value == "PPEWrittenOff"
    assert EventType.PPE_REPLACEMENT_DUE.value == "PPEReplacementDue"


def test_written_off_payload_roundtrip():
    payload = PPEWrittenOffPayload(
        tenant_id="t1",
        ppe_issue_id="i1",
        person_id="p1",
        item_id=None,
        quantity=1,
        reason="износ",
        status="written_off",
    )
    assert payload.model_dump()["reason"] == "износ"


def test_replacement_due_payload_roundtrip():
    payload = PPEReplacementDuePayload(
        tenant_id="t1",
        ppe_issue_id="i1",
        person_id="p1",
        item_id="it1",
        item_name="Каска",
        expires_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        status="due_soon",
    )
    assert payload.model_dump()["item_name"] == "Каска"
