"""Tests for contractors demo seed in bootstrap_demo_tenant.

Verifies that running bootstrap_demo_tenant:
- creates the "contractors" Feature catalogue row,
- results in is_feature_enabled(..., "contractors") == True for the demo tenant,
- seeds at least 2 ContractorEmployee rows under the demo ContractorRegistry,
- is idempotent (re-run does not duplicate the registry or employees).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.feature_flags import is_feature_enabled
from app.models.feature import Feature
from app.models.models import Tenant
from app.modules.contractors.models import ContractorEmployee, ContractorRegistry
from app.services.demo_bootstrap import bootstrap_demo_tenant

_DEMO_TENANT_SLUG = "contractors-bootstrap-demo"
_DEMO_COMPANY = "Contractors Bootstrap Co"
_DEMO_SITE = "Contractors Bootstrap Site"


def _make_settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "DEMO_BOOTSTRAP": True,
            "DEMO_TENANT_ID": _DEMO_TENANT_SLUG,
            "DEMO_COMPANY_NAME": _DEMO_COMPANY,
            "DEMO_SITE_NAME": _DEMO_SITE,
            "LIBREOFFICE_BIN": "python",
        }
    )


@pytest.mark.anyio
async def test_contractors_feature_seeded_and_enabled(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap_demo_tenant seeds the 'contractors' Feature and is_feature_enabled defaults True."""

    async def fake_ensure_default_packs(session, *, tenant_slug: str) -> None:
        return None

    monkeypatch.setattr("app.services.demo_bootstrap.ensure_default_packs", fake_ensure_default_packs)

    await bootstrap_demo_tenant(_make_settings())

    async with sessionmaker() as session:
        # Feature catalogue row exists in the shared (public) schema.
        feature = (
            await session.execute(select(Feature).where(Feature.code == "contractors"))
        ).scalar_one_or_none()
        assert feature is not None, "Feature(code='contractors') must exist after bootstrap"
        assert feature.title == "Подрядчики"

        # Resolve the demo tenant id.
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        # is_feature_enabled defaults True (no FeatureEnablement row needed).
        enabled = await is_feature_enabled(session, tenant_id, "contractors")
        assert enabled is True


@pytest.mark.anyio
async def test_contractors_demo_employees_seeded(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap_demo_tenant seeds at least 2 ContractorEmployee rows for the demo tenant."""

    async def fake_ensure_default_packs(session, *, tenant_slug: str) -> None:
        return None

    monkeypatch.setattr("app.services.demo_bootstrap.ensure_default_packs", fake_ensure_default_packs)

    await bootstrap_demo_tenant(_make_settings())

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        registry = (
            await session.execute(
                select(ContractorRegistry).where(
                    ContractorRegistry.tenant_id == tenant_id,
                    ContractorRegistry.name == "Демо-подрядчик",
                )
            )
        ).scalar_one_or_none()
        assert registry is not None, "ContractorRegistry 'Демо-подрядчик' must exist after bootstrap"
        assert registry.status == "active"

        employee_count = (
            await session.execute(
                select(func.count()).where(ContractorEmployee.contractor_id == registry.id)
            )
        ).scalar_one()
        assert employee_count >= 2, (
            f"Expected at least 2 demo ContractorEmployee rows, got {employee_count}"
        )

        # Verify the two demo employees by name.
        employees = (
            await session.execute(
                select(ContractorEmployee).where(ContractorEmployee.contractor_id == registry.id)
            )
        ).scalars().all()
        names = {e.full_name for e in employees}
        assert "Готовый Иван" in names, "Expected demo employee 'Готовый Иван'"
        assert "Просроченный Пётр" in names, "Expected demo employee 'Просроченный Пётр'"


@pytest.mark.anyio
async def test_contractors_bootstrap_is_idempotent(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running bootstrap does not duplicate ContractorRegistry or ContractorEmployee rows."""

    async def fake_ensure_default_packs(session, *, tenant_slug: str) -> None:
        return None

    monkeypatch.setattr("app.services.demo_bootstrap.ensure_default_packs", fake_ensure_default_packs)

    settings = _make_settings()

    # First run.
    await bootstrap_demo_tenant(settings)

    # Second run — must be idempotent.
    await bootstrap_demo_tenant(settings)

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        registry_count = (
            await session.execute(
                select(func.count()).where(
                    ContractorRegistry.tenant_id == tenant_id,
                    ContractorRegistry.name == "Демо-подрядчик",
                )
            )
        ).scalar_one()
        assert registry_count == 1, (
            f"Expected exactly 1 ContractorRegistry after double-bootstrap, got {registry_count}"
        )

        registry = (
            await session.execute(
                select(ContractorRegistry).where(
                    ContractorRegistry.tenant_id == tenant_id,
                    ContractorRegistry.name == "Демо-подрядчик",
                )
            )
        ).scalar_one()

        employee_count = (
            await session.execute(
                select(func.count()).where(ContractorEmployee.contractor_id == registry.id)
            )
        ).scalar_one()
        assert employee_count == 2, (
            f"Expected exactly 2 ContractorEmployee rows after double-bootstrap, got {employee_count}"
        )

        # Feature row should also not be duplicated (unique constraint enforced, but verify query).
        feature_count = (
            await session.execute(
                select(func.count()).where(Feature.code == "contractors")
            )
        ).scalar_one()
        assert feature_count == 1, (
            f"Expected exactly 1 Feature(code='contractors') after double-bootstrap, got {feature_count}"
        )
