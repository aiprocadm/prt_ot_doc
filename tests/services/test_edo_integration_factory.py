from __future__ import annotations

import pytest

from app.services.integrations import factory as integration_factory
from app.services.integrations.http_edo import HttpEDOIntegration
from app.services.integrations.stubs import DisabledEDOIntegration, StubEDOIntegration


@pytest.fixture(autouse=True)
def _reset_integration_cache():
    integration_factory.reset_integration_providers()
    yield
    integration_factory.reset_integration_providers()


def test_edo_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        app_env = "test"
        use_edo_integration = False
        edo_integration_base_url = "https://should-not-matter"
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    integration_factory.reset_integration_providers()
    client = integration_factory.get_edo_integration()
    assert isinstance(client, DisabledEDOIntegration)


def test_edo_stub_when_flag_on_without_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        app_env = "test"
        use_edo_integration = True
        edo_integration_base_url = None
        edo_integration_api_token = None
        edo_integration_timeout_seconds = 30.0
        edo_integration_outbound_path = "/v1/outbound/documents"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    integration_factory.reset_integration_providers()
    client = integration_factory.get_edo_integration()
    assert isinstance(client, StubEDOIntegration)


def test_edo_http_when_flag_on_with_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        app_env = "test"
        use_edo_integration = True
        edo_integration_base_url = "https://edo.operator.local"
        edo_integration_api_token = "secret"
        edo_integration_timeout_seconds = 12.0
        edo_integration_outbound_path = "/push/doc"

    monkeypatch.setattr(integration_factory, "get_settings", lambda: S())
    integration_factory.reset_integration_providers()
    client = integration_factory.get_edo_integration()
    assert isinstance(client, HttpEDOIntegration)
    assert client._base == "https://edo.operator.local"  # noqa: SLF001
