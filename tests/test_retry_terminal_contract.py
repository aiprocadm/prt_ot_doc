"""Контракт retry vs terminal: согласованность с docs/stabilization/RETRY_VS_TERMINAL_OUTBOX_CELERY.md."""

from __future__ import annotations

import asyncio

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.exc import SQLAlchemyError

from app.services.outbox import OutboxProcessor, OutboxStatus
from app.tasks import RETRYABLE_EXCEPTIONS


def test_celery_autoretry_covers_infra_exception_families() -> None:
    types = set(RETRYABLE_EXCEPTIONS)
    assert ClientError in types
    assert SQLAlchemyError in types
    assert OSError in types
    assert asyncio.TimeoutError in types


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (None, OutboxStatus.FAILED),
        (500, OutboxStatus.FAILED),
        (408, OutboxStatus.FAILED),
        (429, OutboxStatus.FAILED),
        (404, OutboxStatus.DEAD),
        (400, OutboxStatus.DEAD),
    ],
)
def test_outbox_http_classification_matches_doc(status_code: int | None, expected: OutboxStatus) -> None:
    proc = OutboxProcessor.__new__(OutboxProcessor)  # type: ignore[misc]
    assert proc._classify_http_error(status_code) == expected
