"""BIZ-49 срез-14 — чистые правила переноса данных клиента (разд. 49.1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domains.managed_clients.lifecycle import ManagedClientMode
from app.domains.managed_clients.transfer import (
    TransferError,
    is_person_transferable,
    validate_transfer_preconditions,
)

_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def test_dedicated_with_company_and_no_prior_transfer_passes():
    validate_transfer_preconditions(
        mode=ManagedClientMode.DEDICATED,
        dedicated_tenant_slug="romashka",
        company_id="comp-a",
        has_completed_transfer=False,
    )


def test_lightweight_cannot_transfer():
    """Пока клиент Lightweight, у данных один дом — переносить некуда."""
    with pytest.raises(TransferError):
        validate_transfer_preconditions(
            mode=ManagedClientMode.LIGHTWEIGHT,
            dedicated_tenant_slug=None,
            company_id="comp-a",
            has_completed_transfer=False,
        )


def test_dedicated_without_slug_cannot_transfer():
    with pytest.raises(TransferError):
        validate_transfer_preconditions(
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug=None,
            company_id="comp-a",
            has_completed_transfer=False,
        )


def test_missing_company_means_nothing_to_transfer():
    with pytest.raises(TransferError):
        validate_transfer_preconditions(
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug="romashka",
            company_id=None,
            has_completed_transfer=False,
        )


def test_second_transfer_is_rejected():
    """Повторный перенос создал бы неразличимые дубли людей."""
    with pytest.raises(TransferError):
        validate_transfer_preconditions(
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug="romashka",
            company_id="comp-a",
            has_completed_transfer=True,
        )


def test_live_person_is_transferable():
    assert is_person_transferable(deleted_at=None, anonymized_at=None) is True


def test_deleted_person_stays_behind():
    assert is_person_transferable(deleted_at=_NOW, anonymized_at=None) is False


def test_anonymized_person_stays_behind():
    """Копия обезличенного в новом арендаторе — новая обработка ПДн без основания."""
    assert is_person_transferable(deleted_at=None, anonymized_at=_NOW) is False
