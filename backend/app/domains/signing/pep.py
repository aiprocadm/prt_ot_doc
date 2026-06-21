"""PEP (простая электронная подпись, vNext §6.9) — чистый домен.

Канонизация подписываемого содержимого, SHA-256, FSM запроса подписи и
исход проверки разового кода. Без I/O — по образцу domains/ppe/lifecycle.py.
"""
from __future__ import annotations

import enum
import hashlib
import json
from datetime import datetime
from typing import Any

PEP_PURPOSES = frozenset(
    {"document", "acknowledgement", "ppe_issue", "briefing", "work_permit", "work_permit_briefing", "work_permit_closing"}
)
MAX_CONFIRM_ATTEMPTS = 5
CONFIRM_TTL_MINUTES = 15


class PepStatus(str, enum.Enum):
    CREATED = "created"
    AWAITING_CODE = "awaiting_code"
    SIGNED = "signed"
    DECLINED = "declined"
    EXPIRED = "expired"


_TRANSITIONS: dict[PepStatus, frozenset[PepStatus]] = {
    PepStatus.CREATED: frozenset({PepStatus.AWAITING_CODE, PepStatus.SIGNED, PepStatus.DECLINED}),
    PepStatus.AWAITING_CODE: frozenset({PepStatus.SIGNED, PepStatus.DECLINED, PepStatus.EXPIRED}),
    PepStatus.SIGNED: frozenset(),
    PepStatus.DECLINED: frozenset(),
    PepStatus.EXPIRED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


def assert_transition(src: PepStatus, dst: PepStatus) -> None:
    if dst not in _TRANSITIONS[src]:
        raise InvalidTransition(f"pep signature request: {src.value} -> {dst.value}")


def canonical_payload(object_type: str, object_id: str, content: dict[str, Any]) -> str:
    """Каноничный JSON того, ЧТО подписывается: sorted keys, компактно, юникод."""
    return json.dumps(
        {"content": content, "object_id": object_id, "object_type": object_type},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def content_hash(payload: str) -> str:
    """SHA-256 hex digest of the canonical UTF-8 payload string."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_confirm_code(request_id: str, code: str) -> str:
    """Код в БД не хранится: только SHA-256 с солью = id запроса."""
    return hashlib.sha256(f"{request_id}:{code}".encode("utf-8")).hexdigest()


class ConfirmOutcome(str, enum.Enum):
    OK = "ok"
    WRONG_CODE = "wrong_code"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


def confirm_outcome(
    *,
    stored_code_hash: str,
    provided_code: str,
    request_id: str,
    attempts: int,
    expires_at: datetime,
    now: datetime,
) -> ConfirmOutcome:
    """Исход попытки подтверждения. Порядок проверок: TTL → код → счётчик.

    Оба datetime-аргумента обязаны быть timezone-aware.
    """
    if now >= expires_at:
        return ConfirmOutcome.EXPIRED
    if hash_confirm_code(request_id, provided_code) == stored_code_hash:
        return ConfirmOutcome.OK
    if attempts + 1 >= MAX_CONFIRM_ATTEMPTS:
        return ConfirmOutcome.EXHAUSTED
    return ConfirmOutcome.WRONG_CODE
