import asyncio

import pytest

from app.core.config import get_settings, reset_settings_cache
from app.services.integrations import (
    IntegrationDisabledError,
    get_accounting_integration,
    get_edo_integration,
    get_eisot_integration,
    get_frdo_integration,
    reset_integration_providers,
)


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    reset_settings_cache()
    reset_integration_providers()
    for key in [
        "USE_1C_INTEGRATION",
        "USE_EDO_INTEGRATION",
        "USE_FRDO_INTEGRATION",
        "USE_EISOT_INTEGRATION",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield
    reset_settings_cache()
    reset_integration_providers()


@pytest.mark.asyncio
async def test_disabled_integrations_raise():
    accounting = get_accounting_integration()
    edo = get_edo_integration()
    frdo = get_frdo_integration()
    eisot = get_eisot_integration()

    with pytest.raises(IntegrationDisabledError):
        await accounting.health_check()
    with pytest.raises(IntegrationDisabledError):
        await edo.send_document(content=b"sample", filename="doc.txt")
    with pytest.raises(IntegrationDisabledError):
        await frdo.submit_record({"field": "value"})
    with pytest.raises(IntegrationDisabledError):
        await eisot.publish_report({"report": True})


@pytest.mark.asyncio
async def test_stub_integrations_return_status(monkeypatch):
    monkeypatch.setenv("USE_1C_INTEGRATION", "1")
    monkeypatch.setenv("USE_EDO_INTEGRATION", "1")
    monkeypatch.setenv("USE_FRDO_INTEGRATION", "1")
    monkeypatch.setenv("USE_EISOT_INTEGRATION", "1")

    reset_settings_cache()
    settings = get_settings(force_reload=True)
    reset_integration_providers()

    accounting = get_accounting_integration()
    edo = get_edo_integration()
    frdo = get_frdo_integration()
    eisot = get_eisot_integration()

    status_1c = await accounting.export_document({"document_number": "DOC-001"})
    status_edo = await edo.send_document(content=b"data", filename="file.pdf")
    status_frdo = await frdo.submit_record({"person_snils": "123-456-789 01"})
    status_eisot = await eisot.publish_report({"report_period": "2024-01"})

    assert settings.use_1c_integration is True
    assert status_1c.status in {"queued", "processed"}
    assert status_edo.external_id.startswith("edo-")
    assert status_frdo.status == "submitted"
    assert status_eisot.status == "queued"

    statuses = await asyncio.gather(
        accounting.sync_status(status_1c.external_id),
        edo.get_document_status(status_edo.external_id),
        frdo.get_record_status(status_frdo.external_id),
        eisot.get_publication_status(status_eisot.external_id),
    )

    assert all(item.external_id for item in statuses)
