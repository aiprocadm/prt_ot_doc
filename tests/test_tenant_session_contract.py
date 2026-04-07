from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

import app.api.dependencies as api_dependencies
import app.db.session as db_session
from app.core.config import Settings
from app.models.finance import Department
from app.models.models import Company, Person, Position, Site, Tenant, TrainingCourse
from app.services.dev_bootstrap import bootstrap_admin_user
from app.services.demo_bootstrap import bootstrap_demo_tenant
from app.services.tenants.bootstrap.service import BootstrapTenantService


@pytest.mark.anyio
async def test_before_flush_resolves_tenant_uuid_from_session_slug(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        company = Company(name="Invariant Co")
        session.add(company)
        await session.flush()

        assert company.tenant_id == tenant.id


@pytest.mark.anyio
async def test_before_flush_rejects_slug_written_into_uuid_tenant_id(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        company = Company(tenant_id=tenant.slug, name="Broken Tenant Ref")
        session.add(company)

        with pytest.raises(ValueError, match="tenant.id"):
            await session.flush()


@pytest.mark.anyio
async def test_demo_bootstrap_uses_tenant_uuid_for_fk_backed_entities(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_default_packs(session, *, tenant_slug: str) -> None:
        return None

    monkeypatch.setattr("app.services.demo_bootstrap.ensure_default_packs", fake_ensure_default_packs)

    settings = Settings.model_validate(
        {
            "APP_ENV": "test",
            "DEMO_BOOTSTRAP": True,
            "DEMO_TENANT_ID": "wave1-demo",
            "DEMO_COMPANY_NAME": "Wave 1 Demo LLC",
            "DEMO_SITE_NAME": "Wave 1 Site",
            "LIBREOFFICE_BIN": "python",
        }
    )

    await bootstrap_demo_tenant(settings)

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "wave1-demo"))).scalar_one()
        company = (await session.execute(select(Company).where(Company.name == "Wave 1 Demo LLC"))).scalar_one()
        site = (await session.execute(select(Site).where(Site.name == "Wave 1 Site"))).scalar_one()
        department = (await session.execute(select(Department).where(Department.code == "DEMO-PROD"))).scalar_one()
        position = (await session.execute(select(Position).where(Position.name == "Мастер участка"))).scalar_one()
        person = (await session.execute(select(Person).where(Person.personnel_number == "D-001"))).scalar_one()
        course = (await session.execute(select(TrainingCourse).where(TrainingCourse.code == "demo-intro"))).scalar_one()

        assert company.tenant_id == tenant.id
        assert site.tenant_id == tenant.id
        assert department.tenant_id == tenant.id
        assert position.tenant_id == tenant.id
        assert person.tenant_id == tenant.id
        assert course.tenant_id == tenant.id


@pytest.mark.anyio
async def test_async_session_local_ensures_explicit_schema_name(monkeypatch: pytest.MonkeyPatch) -> None:
    ensured: list[tuple[str, str | None, bool]] = []

    monkeypatch.setattr(db_session, "_SUPPORTS_SCHEMAS", True)
    monkeypatch.setattr(db_session, "ensure_shared_schema", lambda *, implicit=False: None)
    monkeypatch.setattr(
        db_session,
        "ensure_tenant_schema",
        lambda slug, *, schema_name=None, implicit=False: ensured.append((slug, schema_name, implicit)),
    )

    session = db_session.AsyncSessionLocal(tenant="schema-demo", schema_name="tenant_schema_demo")
    try:
        assert ensured == [("schema-demo", "tenant_schema_demo", True)]
        assert session.info["search_path"] == ["tenant_schema_demo", "public"]
        assert session.info["tenant_schema"] == "tenant_schema_demo"
    finally:
        await session.close()


@pytest.mark.anyio
async def test_get_tenant_session_hydrates_canonical_session_contract(sessionmaker) -> None:
    async with sessionmaker() as seed:
        tenant = (await seed.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

    async with db_session.get_tenant_session(tenant="test") as session:
        assert session.info["tenant_id"] == tenant.id
        assert session.info["tenant_slug"] == tenant.slug
        assert session.info["tenant_schema"]
        assert session.info["tenant"] == tenant.slug


@pytest.mark.anyio
async def test_get_tenant_session_resets_search_path_on_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []

    class _FakeSession:
        async def execute(self, stmt):
            executed.append(str(stmt))
            return None

    @asynccontextmanager
    async def _fake_session_local(**kwargs):
        yield _FakeSession()

    monkeypatch.setattr(db_session, "_SEARCH_PATH_SUPPORTED", True)
    monkeypatch.setattr(db_session, "_SHARED_SCHEMA", "public")
    monkeypatch.setattr(db_session, "AsyncSessionLocal", _fake_session_local)

    async with db_session.get_tenant_session(tenant="tenant-a", schema_name="tenant_schema_a"):
        pass

    assert any('SET LOCAL search_path TO "tenant_schema_a", "public"' in sql for sql in executed)
    assert any('SET search_path TO "public"' in sql for sql in executed)


@pytest.mark.anyio
async def test_fetch_tenant_by_identifier_uses_recorded_schema_name(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = Tenant(
            slug="schema-demo",
            code="schema-demo",
            name="Schema Demo",
            contact_email="schema-demo@example.local",
            is_active=True,
            schema_name="tenant_schema_demo",
        )
        session.add(tenant)
        await session.commit()

    ensured: list[tuple[str, str | None, bool]] = []
    monkeypatch.setattr(
        api_dependencies,
        "ensure_tenant_schema",
        lambda slug, *, schema_name=None, implicit=False: ensured.append((slug, schema_name, implicit)),
    )

    tenant = await api_dependencies._fetch_tenant_by_identifier("schema-demo")

    assert tenant.slug == "schema-demo"
    assert tenant.schema_name == "tenant_schema_demo"
    assert ensured == [("schema-demo", "tenant_schema_demo", True)]


def test_ensure_tenant_schema_skips_implicit_bootstrap_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_session, "_SUPPORTS_SCHEMAS", True)
    monkeypatch.setattr(
        db_session,
        "_settings",
        type("Settings", (), {"app_env": "development", "runtime_schema_bootstrap": False})(),
    )
    monkeypatch.setattr(db_session, "_tenant_initialized", set())

    triggered: list[str] = []
    monkeypatch.setattr(db_session, "_run_in_thread", lambda fn: triggered.append("called"))

    db_session.ensure_tenant_schema("demo", implicit=True)

    assert triggered == []


def test_ensure_tenant_schema_allows_explicit_bootstrap_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_session, "_SUPPORTS_SCHEMAS", True)
    monkeypatch.setattr(
        db_session,
        "_settings",
        type("Settings", (), {"app_env": "development", "runtime_schema_bootstrap": False})(),
    )
    monkeypatch.setattr(db_session, "_tenant_initialized", set())

    triggered: list[str] = []
    monkeypatch.setattr(db_session, "_run_in_thread", lambda fn: triggered.append("called"))

    db_session.ensure_tenant_schema("demo", implicit=False)

    assert triggered == ["called"]


@pytest.mark.anyio
async def test_dev_bootstrap_uses_recorded_schema_name(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = Tenant(
            slug="admin-demo",
            code="admin-demo",
            name="Admin Demo",
            contact_email="admin-demo@example.local",
            is_active=True,
            schema_name="tenant_schema_admin_demo",
        )
        session.add(tenant)
        await session.commit()

    ensured: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "app.services.dev_bootstrap.ensure_tenant_schema",
        lambda slug, *, schema_name=None: ensured.append((slug, schema_name)),
    )

    settings = Settings.model_validate(
        {
            "APP_ENV": "test",
            "ADMIN_BOOTSTRAP": True,
            "ADMIN_TENANT": "admin-demo",
            "ADMIN_EMAIL": "admin@example.local",
            "ADMIN_PASSWORD": "secret123",
            "LIBREOFFICE_BIN": "python",
        }
    )

    await bootstrap_admin_user(settings)

    assert ensured == [("admin-demo", "tenant_schema_admin_demo")]


@pytest.mark.anyio
async def test_tenant_bootstrap_service_uses_recorded_schema_name_for_existing_tenant(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = Tenant(
            slug="existing-bootstrap",
            code="existing-bootstrap",
            name="Existing Bootstrap",
            contact_email="owner@example.local",
            is_active=True,
            schema_name="tenant_schema_existing_bootstrap",
        )
        session.add(tenant)
        await session.commit()

    ensured: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "app.services.tenants.bootstrap.service.ensure_tenant_schema",
        lambda slug, *, schema_name=None: ensured.append((slug, schema_name)),
    )

    async def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("app.services.tenants.bootstrap.service.seed_authz_catalog", _noop)

    async with sessionmaker() as session:
        service = BootstrapTenantService(session)
        monkeypatch.setattr(service, "_ensure_tenant_settings", _noop)
        monkeypatch.setattr(service, "_ensure_quota", _noop)
        monkeypatch.setattr(service, "_ensure_owner", _noop)
        monkeypatch.setattr(service, "_ensure_company_profile", _noop)
        monkeypatch.setattr(service, "_seed_starter_pack", _noop)
        monkeypatch.setattr(service, "_seed_package_presets", _noop)
        monkeypatch.setattr(service, "_log_bootstrap_event", _noop)
        await service.run(
            tenant_slug="existing-bootstrap",
            tenant_name="Existing Bootstrap",
            owner_email="owner@example.local",
            owner_password="secret123",
        )

    assert ensured == [("existing-bootstrap", "tenant_schema_existing_bootstrap")]