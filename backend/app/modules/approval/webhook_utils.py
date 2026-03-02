from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


def build_webhook_signature(*, secret: str, body: bytes) -> str:
    """Build HMAC SHA256 signature for outbound/inbound webhook payloads."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def build_edo_status_dedup_key(*, external_id: str, status: str, event_time: datetime | None = None) -> str:
    """Deduplicate EDO status transitions in minute buckets."""
    ts = event_time or datetime.now(timezone.utc)
    bucket = ts.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
    return f"{external_id}:{status}:{bucket}"

