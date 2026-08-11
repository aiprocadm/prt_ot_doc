"""BIZ-49 срез-12 — чистые правила согласия клиента (разд. 49.3 + 66.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.managed_clients.consent import (
    ClientConsent,
    ConsentInvalid,
    ConsentRequired,
    active_consent,
    is_consent_active,
    require_active_consent,
    validate_consent,
)

_NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _consent(**kw) -> ClientConsent:
    base = dict(
        client_id="c1",
        document_ref="Поручение №1",
        granted_at=_NOW - timedelta(days=1),
        expires_at=None,
        revoked_at=None,
    )
    base.update(kw)
    return ClientConsent(**base)


# --- validate ---------------------------------------------------------------
def test_validate_requires_document_ref():
    """Согласие «на словах» не основание."""
    with pytest.raises(ConsentInvalid):
        validate_consent(document_ref="   ", granted_at=_NOW, expires_at=None)


def test_validate_rejects_expiry_before_grant():
    with pytest.raises(ConsentInvalid):
        validate_consent(
            document_ref="Поручение №1", granted_at=_NOW, expires_at=_NOW - timedelta(days=1)
        )


def test_validate_accepts_open_ended():
    validate_consent(document_ref="Поручение №1", granted_at=_NOW, expires_at=None)


# --- is_active --------------------------------------------------------------
def test_active_when_not_revoked_and_not_expired():
    assert is_consent_active(_consent(), now=_NOW) is True


def test_revoked_is_inactive():
    assert is_consent_active(_consent(revoked_at=_NOW - timedelta(hours=1)), now=_NOW) is False


def test_expired_equals_revoked():
    """Срок в документе — часть волеизъявления клиента."""
    assert is_consent_active(_consent(expires_at=_NOW - timedelta(minutes=1)), now=_NOW) is False


def test_expiry_boundary_is_inactive():
    """Ровно в момент истечения согласие уже не действует."""
    assert is_consent_active(_consent(expires_at=_NOW), now=_NOW) is False


def test_future_expiry_is_active():
    assert is_consent_active(_consent(expires_at=_NOW + timedelta(days=30)), now=_NOW) is True


# --- require ----------------------------------------------------------------
def test_require_raises_without_any_consent():
    with pytest.raises(ConsentRequired):
        require_active_consent([], now=_NOW)


def test_require_raises_when_all_revoked_or_expired():
    consents = [
        _consent(revoked_at=_NOW - timedelta(hours=2)),
        _consent(expires_at=_NOW - timedelta(hours=1)),
    ]
    with pytest.raises(ConsentRequired):
        require_active_consent(consents, now=_NOW)


def test_require_passes_when_one_active_among_dead():
    """Продление новым документом до истечения старого — штатный случай."""
    consents = [
        _consent(revoked_at=_NOW - timedelta(days=2)),
        _consent(document_ref="Поручение №2"),
    ]
    got = require_active_consent(consents, now=_NOW)
    assert got.document_ref == "Поручение №2"


def test_active_consent_returns_none_when_empty():
    assert active_consent([], now=_NOW) is None
