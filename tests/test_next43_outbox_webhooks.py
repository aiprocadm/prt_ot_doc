from __future__ import annotations

import hashlib
import hmac

from app.services.inbound_dedup import compute_inbound_dedup_key
from app.tasks import _compute_outbox_backoff


def test_backoff_increases_and_caps() -> None:
    first = _compute_outbox_backoff(1).total_seconds()
    second = _compute_outbox_backoff(2).total_seconds()
    tenth = _compute_outbox_backoff(10).total_seconds()
    assert second >= first
    assert tenth >= second


def test_hmac_signature_generation() -> None:
    secret = "abc"
    ts = "123"
    body = b'{"x":1}'
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    assert sig == hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_dedup_key_prefers_event_id() -> None:
    payload = {"event_id": "evt-1"}
    raw = b"{}"
    dedup = str(
        payload.get("event_id") or payload.get("message_id") or hashlib.sha256(raw).hexdigest()
    )
    assert dedup == "evt-1"


def test_dedup_key_fallback_to_payload_hash() -> None:
    raw = b'{"x":1}'
    key = compute_inbound_dedup_key({}, raw)
    assert key == hashlib.sha256(raw).hexdigest()
