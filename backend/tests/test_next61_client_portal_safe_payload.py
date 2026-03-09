from app.modules.client_portal.services import SafePortalPayloadService


def test_safe_payload_strips_internal_fields() -> None:
    source = {
        "status": "ready",
        "internal_notes": "secret",
        "audit_payload": {"raw": 1},
        "risk_formula": "a*b",
        "public_link": "ok",
    }

    safe = SafePortalPayloadService.sanitize(source)

    assert safe == {"status": "ready", "public_link": "ok"}


def test_safe_payload_strips_nested_internal_fields() -> None:
    source = {
        "status": "ready",
        "checklist": [
            {"name": "public", "internal_notes": "hide"},
            {"name": "second", "nested": {"audit_payload": {"secret": 1}, "ok": True}},
        ],
        "nested": {
            "public_link": "ok",
            "policy_payload": {"internal": "x"},
        },
    }

    safe = SafePortalPayloadService.sanitize(source)

    assert safe == {
        "status": "ready",
        "checklist": [
            {"name": "public"},
            {"name": "second", "nested": {"ok": True}},
        ],
        "nested": {"public_link": "ok"},
    }


def test_safe_payload_handles_none_payload() -> None:
    assert SafePortalPayloadService.sanitize(None) == {}
