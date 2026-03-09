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
