from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import pytest

from app.api.routes.integration_readiness import _provider_health, get_integration_readiness
from app.core.security import AccessContext
from app.services.integrations.interfaces import IntegrationDisabledError


@pytest.mark.asyncio
async def test_provider_health_marks_stub_integrations_as_non_production(monkeypatch) -> None:
    class StubProvider:
        name = "stub-edo"

        async def health_check(self) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routes.integration_readiness.get_edo_integration",
        lambda: StubProvider(),
    )

    payload = await _provider_health("edo")

    assert payload["adapter"] == "stub-edo"
    assert payload["provider_mode"] == "non_production"
    assert payload["provider_production_ready"] is False
    assert payload["health_status"] == "ready"


@pytest.mark.asyncio
async def test_integration_readiness_returns_summary_with_provider_modes(monkeypatch) -> None:
    tenant = SimpleNamespace(id="tenant-1")
    user = SimpleNamespace(id="user-1", email="owner@test", role=SimpleNamespace(value="owner"))
    access = AccessContext(
        user=user,
        claims=MappingProxyType({"sub": user.id, "tenant_id": tenant.id, "roles": ["owner"]}),
        tenant_slug="tenant-a",
        tenant_id=tenant.id,
        company_id=None,
    )

    class StubAccounting:
        name = "stub-1c"

        async def health_check(self) -> bool:
            return True

    class DisabledEdo:
        name = "disabled-edo"

        async def health_check(self) -> bool:
            raise IntegrationDisabledError("EDO integration is disabled")

    class ProductionCandidate:
        def __init__(self, name: str):
            self.name = name

        async def health_check(self) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routes.integration_readiness.get_accounting_integration", lambda: StubAccounting()
    )
    monkeypatch.setattr(
        "app.api.routes.integration_readiness.get_edo_integration", lambda: DisabledEdo()
    )
    monkeypatch.setattr(
        "app.api.routes.integration_readiness.get_frdo_integration",
        lambda: ProductionCandidate("kontur-frdo"),
    )
    monkeypatch.setattr(
        "app.api.routes.integration_readiness.get_eisot_integration",
        lambda: ProductionCandidate("kontur-eisot"),
    )

    class ScalarRows:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return self

        def all(self):
            return self._values

    class TupleRow:
        def __init__(self, values):
            self._values = values

        def one(self):
            return self._values

    class FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return ScalarRows([])
            if self.calls == 2:
                return TupleRow((0, 0))
            if self.calls == 3:
                return TupleRow((0, 0, 0))
            raise AssertionError(f"Unexpected execute call: {self.calls}")

    payload = await get_integration_readiness(access, tenant=tenant, session=FakeSession())

    assert payload["tenant_id"] == tenant.id
    assert payload["summary"]["non_production_total"] == 2
    assert payload["summary"]["disabled_total"] == 1
    assert payload["summary"]["production_ready_total"] >= 3
    providers = {item["provider"]: item for item in payload["providers"]}
    assert providers["1c"]["provider_mode"] == "non_production"
    assert providers["edo"]["provider_mode"] == "non_production"
    assert providers["edo"]["health_status"] == "disabled"
    assert providers["frdo"]["provider_mode"] == "production_candidate"
    assert providers["ldap"]["health_status"] == "contract_only"
