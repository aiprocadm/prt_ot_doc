from __future__ import annotations

from app.services.events import EventType, dedupe_key_for, normalize_payload


def test_incident_created_payload_is_normalized_and_deduped() -> None:
    payload, normalized = normalize_payload(
        event_type=EventType.INCIDENT_CREATED,
        tenant_id="t1",
        payload={
            "incident_id": "inc-1",
            "company_id": "comp-1",
            "site_id": "site-1",
            "status": "reported",
            "severity": "high",
            "incident_type": "near_miss",
        },
    )

    assert normalized["tenant_id"] == "t1"
    assert normalized["incident_id"] == "inc-1"
    assert dedupe_key_for(EventType.INCIDENT_CREATED, payload) == "inc-1"


def test_inspection_created_payload_is_normalized_and_deduped() -> None:
    payload, normalized = normalize_payload(
        event_type=EventType.INSPECTION_CREATED,
        tenant_id="t1",
        payload={
            "inspection_id": "insp-1",
            "company_id": "comp-1",
            "status": "planned",
            "inspection_type": "internal",
            "authority": "RPN",
        },
    )

    assert normalized["tenant_id"] == "t1"
    assert normalized["inspection_id"] == "insp-1"
    assert dedupe_key_for(EventType.INSPECTION_CREATED, payload) == "insp-1"


def test_prescription_overdue_payload_is_normalized_and_deduped() -> None:
    payload, normalized = normalize_payload(
        event_type=EventType.PRESCRIPTION_OVERDUE,
        tenant_id="t1",
        payload={
            "prescription_id": "pre-1",
            "inspection_id": "insp-1",
            "status": "open",
            "assignee_id": "user-1",
        },
    )

    assert normalized["tenant_id"] == "t1"
    assert normalized["prescription_id"] == "pre-1"
    assert dedupe_key_for(EventType.PRESCRIPTION_OVERDUE, payload) == "pre-1"
