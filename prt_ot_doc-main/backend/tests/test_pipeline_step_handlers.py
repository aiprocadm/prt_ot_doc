from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.integrations.interfaces import IntegrationDisabledError, IntegrationStatus
from app.services.pipeline_step_handlers import edo_step_handler


@pytest.mark.asyncio
async def test_edo_step_handler_uses_internal_fallback_when_provider_disabled(monkeypatch) -> None:
    class DisabledProvider:
        name = "disabled-edo"

        async def send_document(self, *, content: bytes, filename: str, metadata: dict):
            raise IntegrationDisabledError("EDO integration is disabled")

    monkeypatch.setattr(
        "app.services.pipeline_step_handlers.get_edo_integration",
        lambda: DisabledProvider(),
    )

    job = SimpleNamespace(
        id="job-1",
        tenant_id="tenant-1",
        template_code="tpl-1",
        input_payload_json={"doc": "v1"},
        correlation_id="corr-1",
    )
    step = SimpleNamespace(id="step-1")

    payload = await edo_step_handler(job=job, step=step)

    assert payload["status"] == "completed"
    assert payload["deferred"] is False
    assert payload["provider"] == "disabled-edo"
    assert payload["reason"] == "edo_integration_disabled"
    assert payload["provider_mode"] == "non_production"
    assert payload["bridge_mode"] == "internal-fallback"


@pytest.mark.asyncio
async def test_edo_step_handler_returns_provider_status_when_enabled(monkeypatch) -> None:
    class EnabledProvider:
        name = "stub-edo"

        async def send_document(self, *, content: bytes, filename: str, metadata: dict):
            return IntegrationStatus(
                external_id="edo-123",
                status="sent",
                details={"ok": True},
            )

    monkeypatch.setattr(
        "app.services.pipeline_step_handlers.get_edo_integration",
        lambda: EnabledProvider(),
    )

    job = SimpleNamespace(
        id="job-2",
        tenant_id="tenant-1",
        template_code="tpl-2",
        input_payload_json={"doc": "v2"},
        correlation_id="corr-2",
    )
    step = SimpleNamespace(id="step-2")

    payload = await edo_step_handler(job=job, step=step)

    assert payload["status"] == "sent"
    assert payload["deferred"] is False
    assert payload["provider"] == "stub-edo"
    assert payload["external_id"] == "edo-123"
    assert payload["details"] == {"ok": True}
