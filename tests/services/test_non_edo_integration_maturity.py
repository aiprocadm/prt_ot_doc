from __future__ import annotations

import pytest

from app.services.integrations import factory as integration_factory
from app.services.integrations.interfaces import IntegrationContractError
from app.services.integrations.pilot_adapters import (
    PilotAccountingIntegration,
    PilotEISOTIntegration,
    PilotFRDOIntegration,
)
from app.services.integrations.stubs import (
    DisabledAccountingIntegration,
    DisabledEISOTIntegration,
    DisabledFRDOIntegration,
)


@pytest.fixture(autouse=True)
def _reset_integration_cache():
    integration_factory.reset_integration_providers()
    yield
    integration_factory.reset_integration_providers()


def test_1c_pilot_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        use_1c_integration = True
        use_edo_integration = False
        edo_integration_base_url = None
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"
        use_frdo_integration = False
        use_eisot_integration = False
        app_env = "test"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    client = integration_factory.get_accounting_integration()
    assert isinstance(client, PilotAccountingIntegration)


def test_1c_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        use_1c_integration = False
        use_edo_integration = False
        edo_integration_base_url = None
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"
        use_frdo_integration = False
        use_eisot_integration = False
        app_env = "test"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    client = integration_factory.get_accounting_integration()
    assert isinstance(client, DisabledAccountingIntegration)


def test_frdo_pilot_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        use_1c_integration = False
        use_edo_integration = False
        edo_integration_base_url = None
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"
        use_frdo_integration = True
        use_eisot_integration = False
        app_env = "test"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    client = integration_factory.get_frdo_integration()
    assert isinstance(client, PilotFRDOIntegration)


def test_eisot_pilot_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        use_1c_integration = False
        use_edo_integration = False
        edo_integration_base_url = None
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"
        use_frdo_integration = False
        use_eisot_integration = True
        app_env = "test"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    client = integration_factory.get_eisot_integration()
    assert isinstance(client, PilotEISOTIntegration)


@pytest.mark.anyio
async def test_pilot_adapters_expose_feature_flag_and_contract_error() -> None:
    one_c = PilotAccountingIntegration()
    with pytest.raises(IntegrationContractError) as exc_info:
        await one_c.export_document({})
    assert exc_info.value.contract.code == "validation_error"
    assert exc_info.value.contract.details["field"] == "document_number"

    frdo = PilotFRDOIntegration()
    status = await frdo.submit_record({"person_snils": "123-456-789 00"})
    assert status.details["maturity"] == "pilot"
    assert status.details["feature_flag"] == "USE_FRDO_INTEGRATION"

    eisot = PilotEISOTIntegration()
    notices = await eisot.pull_notifications()
    assert notices[0].details["maturity"] == "pilot"
    assert notices[0].details["feature_flag"] == "USE_EISOT_INTEGRATION"


def test_disabled_variants_still_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        use_1c_integration = False
        use_edo_integration = False
        edo_integration_base_url = None
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"
        use_frdo_integration = False
        use_eisot_integration = False
        app_env = "test"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    assert isinstance(integration_factory.get_frdo_integration(), DisabledFRDOIntegration)
    assert isinstance(integration_factory.get_eisot_integration(), DisabledEISOTIntegration)

