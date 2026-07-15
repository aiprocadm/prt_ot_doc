"""Unit: каталог событий (интроспекция payload-моделей) + rule.triggered событие."""

from __future__ import annotations

from app.modules.rules_engine.catalog import event_catalog, known_event_types, known_fields_for
from app.services.events import EventType, RuleTriggeredPayload, dedupe_key_for


def test_catalog_covers_registered_events_except_rule_triggered():
    types_ = known_event_types()
    assert "IncidentCreated" in types_
    assert "rule.triggered" not in types_
    # Legacy-алиасы исключены: outbox персистит только канонические значения,
    # правило на алиас было бы мёртвым.
    assert "Signed" not in types_
    assert "Exported" not in types_
    assert "DocumentSigned" in types_
    assert "DocumentExported" in types_


def test_incident_fields_and_kinds():
    incident = next(i for i in event_catalog() if i["event_type"] == "IncidentCreated")
    by_name = {f["name"]: f["kind"] for f in incident["fields"]}
    assert by_name["severity"] == "string"
    assert by_name["occurred_at"] == "datetime"
    assert "tenant_id" in by_name


def test_known_fields_for_unknown_event():
    assert known_fields_for("NoSuchEvent") is None


def test_rule_triggered_payload_dedupe():
    payload = RuleTriggeredPayload(
        tenant_id="t1",
        rule_id="r1",
        rule_name="R",
        source_event_type="IncidentCreated",
        source_event_key="inc-1",
    )
    assert dedupe_key_for(EventType.RULE_TRIGGERED, payload) == "rule-triggered:r1:inc-1"


def test_rule_triggered_normalizes():
    from app.services.events import normalize_payload

    parsed, dumped = normalize_payload(
        event_type=EventType.RULE_TRIGGERED,
        payload={
            "tenant_id": "t1",
            "rule_id": "r1",
            "rule_name": "R",
            "source_event_type": "IncidentCreated",
            "source_event_key": "inc-1",
            "source_payload": {"a": 1},
        },
        tenant_id="t1",
    )
    assert dumped["rule_id"] == "r1"
    assert dumped["source_payload"] == {"a": 1}
