from __future__ import annotations

from app.services.events import (
    EventType,
    MedicalExamRecordedPayload,
    PersonReinstatedPayload,
    PersonSuspendedPayload,
    dedupe_key_for,
    normalize_payload,
)


def test_medical_event_types_registered():
    assert EventType.MEDICAL_EXAM_RECORDED.value == "MedicalExamRecorded"
    assert EventType.PERSON_SUSPENDED.value == "PersonSuspended"
    assert EventType.PERSON_REINSTATED.value == "PersonReinstated"


def test_medical_payload_normalize_and_dedupe():
    parsed, dumped = normalize_payload(
        event_type=EventType.MEDICAL_EXAM_RECORDED,
        payload={"tenant_id": "t1", "exam_id": "e1", "person_id": "p1",
                 "exam_kind": "periodic", "fitness": "fit",
                 "valid_until": "2027-01-01"},
        tenant_id="t1",
    )
    assert isinstance(parsed, MedicalExamRecordedPayload)
    assert dedupe_key_for(EventType.MEDICAL_EXAM_RECORDED, parsed) == "e1"

    parsed2, _ = normalize_payload(
        event_type=EventType.PERSON_SUSPENDED,
        payload={"tenant_id": "t1", "suspension_id": "s1", "person_id": "p1",
                 "reason": "unfit"},
        tenant_id="t1",
    )
    assert dedupe_key_for(EventType.PERSON_SUSPENDED, parsed2) == "s1"

    parsed3, _ = normalize_payload(
        event_type=EventType.PERSON_REINSTATED,
        payload={"tenant_id": "t1", "suspension_id": "s1", "person_id": "p1"},
        tenant_id="t1",
    )
    assert dedupe_key_for(EventType.PERSON_REINSTATED, parsed3) == "s1"
