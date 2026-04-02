from datetime import datetime, timezone

from app.modules.approval.webhook_utils import build_edo_status_dedup_key, build_webhook_signature


def test_webhook_hmac_signature_is_deterministic() -> None:
    body = b'{"event":"Signed"}'
    sig1 = build_webhook_signature(secret="s3cr3t", body=body)
    sig2 = build_webhook_signature(secret="s3cr3t", body=body)
    assert sig1 == sig2


def test_edo_status_dedup_uses_time_bucket() -> None:
    ts = datetime(2026, 3, 2, 12, 5, 40, tzinfo=timezone.utc)
    key = build_edo_status_dedup_key(external_id="ext-1", status="accepted", event_time=ts)
    assert key == "ext-1:accepted:202603021205"
