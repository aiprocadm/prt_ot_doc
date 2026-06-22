"""Ключ дедупликации входящих webhooks (вынесено из Celery core для тонких HTTP handlers)."""

from __future__ import annotations

import hashlib
from typing import Any


def compute_inbound_dedup_key(payload: dict[str, Any], raw_body: bytes) -> str:
    return str(
        payload.get("event_id") or payload.get("message_id") or hashlib.sha256(raw_body).hexdigest()
    )
