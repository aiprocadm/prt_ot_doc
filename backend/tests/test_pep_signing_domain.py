"""PEP (simple e-signature) pure domain: canonical hash, FSM, confirm-code outcome.

Hermetic: no DB, no routes (route-importing tests are un-collectable on this machine).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.signing.pep import (
    CONFIRM_TTL_MINUTES,
    MAX_CONFIRM_ATTEMPTS,
    PEP_PURPOSES,
    ConfirmOutcome,
    InvalidTransition,
    PepStatus,
    assert_transition,
    canonical_payload,
    confirm_outcome,
    content_hash,
    hash_confirm_code,
)

NOW = datetime.now(tz=timezone.utc)


def test_canonical_payload_is_stable_and_key_sorted():
    a = canonical_payload("document_version", "dv-1", {"b": 2, "a": 1})
    b = canonical_payload("document_version", "dv-1", {"a": 1, "b": 2})
    assert a == b
    assert a == '{"content":{"a":1,"b":2},"object_id":"dv-1","object_type":"document_version"}'


def test_canonical_payload_keeps_unicode_readable():
    payload = canonical_payload("ppe_issue", "i-1", {"item_name": "Каска"})
    assert "Каска" in payload  # ensure_ascii=False


def test_content_hash_is_sha256_hex():
    h = content_hash("payload")
    assert len(h) == 64
    assert h == content_hash("payload")
    assert h != content_hash("payload2")


def test_hash_confirm_code_salts_with_request_id():
    assert hash_confirm_code("req-1", "123456") != hash_confirm_code("req-2", "123456")
    assert hash_confirm_code("req-1", "123456") == hash_confirm_code("req-1", "123456")


def test_valid_transitions_pass():
    assert_transition(PepStatus.CREATED, PepStatus.SIGNED)
    assert_transition(PepStatus.CREATED, PepStatus.AWAITING_CODE)
    assert_transition(PepStatus.CREATED, PepStatus.DECLINED)
    assert_transition(PepStatus.AWAITING_CODE, PepStatus.SIGNED)
    assert_transition(PepStatus.AWAITING_CODE, PepStatus.DECLINED)
    assert_transition(PepStatus.AWAITING_CODE, PepStatus.EXPIRED)


@pytest.mark.parametrize(
    "src,dst",
    [
        (PepStatus.SIGNED, PepStatus.DECLINED),
        (PepStatus.DECLINED, PepStatus.SIGNED),
        (PepStatus.EXPIRED, PepStatus.SIGNED),
        (PepStatus.CREATED, PepStatus.EXPIRED),  # expire only from awaiting_code
    ],
)
def test_invalid_transitions_raise(src, dst):
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def _outcome(*, code="123456", stored_code="123456", attempts=0, expired=False):
    expires_at = NOW + (timedelta(minutes=-1) if expired else timedelta(minutes=5))
    return confirm_outcome(
        stored_code_hash=hash_confirm_code("req-1", stored_code),
        provided_code=code,
        request_id="req-1",
        attempts=attempts,
        expires_at=expires_at,
        now=NOW,
    )


def test_confirm_ok():
    assert _outcome() is ConfirmOutcome.OK


def test_confirm_wrong_code():
    assert _outcome(code="999999") is ConfirmOutcome.WRONG_CODE


def test_confirm_expired_wins_over_wrong_code():
    assert _outcome(code="999999", expired=True) is ConfirmOutcome.EXPIRED


def test_confirm_last_attempt_exhausts():
    # attempts уже сделанных = MAX-1; этот неверный ввод — последний
    assert _outcome(code="999999", attempts=MAX_CONFIRM_ATTEMPTS - 1) is ConfirmOutcome.EXHAUSTED


def test_purposes_vocabulary():
    assert {"document", "acknowledgement", "ppe_issue", "briefing"}.issubset(PEP_PURPOSES)
    assert CONFIRM_TTL_MINUTES == 15
    assert MAX_CONFIRM_ATTEMPTS == 5


def test_pep_purposes_include_work_permit_streams():
    from app.domains.signing.pep import PEP_PURPOSES

    assert "work_permit" in PEP_PURPOSES
    assert "work_permit_briefing" in PEP_PURPOSES


def test_confirm_expires_at_exact_boundary():
    # now == expires_at → уже истёк (lazy expiry contract)
    result = confirm_outcome(
        stored_code_hash=hash_confirm_code("req-1", "123456"),
        provided_code="123456",
        request_id="req-1",
        attempts=0,
        expires_at=NOW,
        now=NOW,
    )
    assert result is ConfirmOutcome.EXPIRED
