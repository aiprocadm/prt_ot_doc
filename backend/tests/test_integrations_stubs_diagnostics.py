from __future__ import annotations

import pytest

from app.services.integrations.stubs import (
    StubAccountingIntegration,
    StubEISOTIntegration,
    StubFRDOIntegration,
)


def _assert_non_production_details(details: dict, *, provider: str, operation: str) -> None:
    assert details["provider_mode"] == "non_production"
    assert details["adapter_type"] == "stub"
    assert details["provider"] == provider
    assert details["operation"] == operation
    assert "generated_at" in details


@pytest.mark.asyncio
async def test_stub_accounting_export_has_non_production_details() -> None:
    provider = StubAccountingIntegration()

    status = await provider.export_document({"doc_id": "d-1"})

    _assert_non_production_details(
        status.details, provider=provider.name, operation="export_document"
    )
    assert status.details["received"] is True


def test_stub_edo_integration_removed() -> None:
    """ЭДО-стаб удалён: симуляция отправки документов больше не существует в кодовой базе."""
    import app.services.integrations.stubs as stubs

    assert not hasattr(stubs, "StubEDOIntegration")


@pytest.mark.asyncio
async def test_stub_frdo_submit_has_non_production_details() -> None:
    provider = StubFRDOIntegration()

    status = await provider.submit_record({"record": "r-1"})

    _assert_non_production_details(
        status.details, provider=provider.name, operation="submit_record"
    )
    assert status.details["payload"] == {"record": "r-1"}


@pytest.mark.asyncio
async def test_stub_eisot_publish_has_non_production_details() -> None:
    provider = StubEISOTIntegration()

    status = await provider.publish_report({"report": "rp-1"})

    _assert_non_production_details(
        status.details, provider=provider.name, operation="publish_report"
    )
    assert status.details["payload"] == {"report": "rp-1"}
