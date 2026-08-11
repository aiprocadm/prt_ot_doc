"""PEP events are first-class citizens of the outbox pipeline (sibling parity
with PPEWrittenOff/PPEReplacementDue registration, СИЗ Срез-1)."""
from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

from app.services.events import (  # noqa: E402
    _PAYLOADS,
    EventType,
    PEPDeclinedPayload,
    PEPSignedPayload,
    dedupe_key_for,
)
from app.services.outbox import PipelineType, _pipeline_for_event  # noqa: E402


def test_event_types_registered():
    assert EventType.PEP_SIGNED.value == "PEPSigned"
    assert EventType.PEP_DECLINED.value == "PEPDeclined"
    assert _PAYLOADS[EventType.PEP_SIGNED] is PEPSignedPayload
    assert _PAYLOADS[EventType.PEP_DECLINED] is PEPDeclinedPayload


def test_dedupe_keys():
    signed = PEPSignedPayload(
        tenant_id="t1", signature_request_id="sr-1", object_type="ppe_issue",
        object_id="i-1", purpose="ppe_issue", signer_user_id=None, signer_person_id="p-1",
    )
    declined = PEPDeclinedPayload(tenant_id="t1", signature_request_id="sr-1", reason="manual")
    assert dedupe_key_for(EventType.PEP_SIGNED, signed) == "sr-1:pep_signed"
    assert dedupe_key_for(EventType.PEP_DECLINED, declined) == "sr-1:pep_declined"


def test_pipeline_routing():
    assert _pipeline_for_event("PEPSigned") is PipelineType.DOCUMENT
    assert _pipeline_for_event("PEPDeclined") is PipelineType.DOCUMENT
