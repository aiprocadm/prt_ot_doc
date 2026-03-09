from __future__ import annotations


class SafePortalPayloadService:
    """Strip internal/sensitive fields for client cabinet payloads."""

    _BLOCKED_KEYS = {
        "internal_notes",
        "audit_payload",
        "raw_attempts",
        "raw_answers",
        "risk_formula",
        "system_error",
    }

    @classmethod
    def sanitize(cls, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k not in cls._BLOCKED_KEYS}
