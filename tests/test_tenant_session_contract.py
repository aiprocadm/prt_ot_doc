from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

import app.api.dependencies as api_dependencies
import app.db.session as db_session
from app.core.config import Settings
from app.core.tenant import tenant_context
from app.models.finance import Department
from app.models.models import Company, Person, Position, Site, Tenant, TrainingCourse
from app.services.demo_bootstrap import bootstrap_demo_tenant
from app.services.dev_bootstrap import bootstrap_admin_user
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
async def test_session_scope_accepts_tenant_uuid_for_new_tenant_scoped_rows(sessionmaker) -> None:
    """Regression: celery tasks pass tenant UUID where a slug is expected.

    ``audit_export_job``/``report_export_job`` invoke
    ``tenant_context(tenant_id)`` + ``ensure_tenant_schema(tenant_id)`` +
    ``session_scope(tenant=tenant_id)`` with ``tenant_id=str(tenant.id)``.
    Hydration must detect the UUID mislabelled as ``tenant_slug`` and resolve
    the real tenant identity; otherwise ``_apply_default_tenant`` rejects
    legitimate new rows whose ``tenant_id`` equals that UUID ("must store
    tenant.id, not tenant.slug" — both fields hold the same UUID).
    """

    async with sessionmaker() as seed:
        tenant = (await seed.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

    tenant_uuid = str(tenant.id)
    with tenant_context(tenant_uuid):
        db_session.ensure_tenant_schema(tenant_uuid)
        async with db_session.session_scope(tenant=tenant_uuid) as session:
            explicit = Company(tenant_id=tenant.id, name="UUID Tenant Explicit Row")
            auto = Company(name="UUID Tenant Auto Row")
            session.add_all([explicit, auto])
            await session.flush()

            assert explicit.tenant_id == tenant.id
            assert auto.tenant_id == tenant.id
            assert session.info["tenant_id"] == tenant.id
            assert session.info["tenant_slug"] == tenant.slug
            assert session.info["tenant"] == tenant.slug


@pytest.mark.anyio
async def test_before_flush_ignores_tenant_uuid_mislabelled_as_slug(sessionmaker) -> None:
    """Same bug, sync path: sessions that skip ``__aenter__`` hydration must
    still not treat a UUID stored in ``session.info["tenant_slug"]`` as a slug
    inside the before_flush guard."""

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant_id"] = tenant.id
        session.info["tenant_slug"] = str(tenant.id)
        session.info["tenant_schema"] = "public"

        company = Company(tenant_id=tenant.id, name="Guard UUID Slug Row")
        session.add(company)
        await session.flush()

        assert company.tenant_id == tenant.id
        assert session.info["tenant_slug"] == tenant.slug


@pytest.mark.anyio
async def test_demo_bootstrap_uses_tenant_uuid_for_fk_backed_entities(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_default_packs(session, *, tenant_slug: str) -> None:
        return None

    monkeypatch.setattr(
        "app.services.demo_bootstrap.ensure_default_packs", fake_ensure_default_packs
    )

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
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "wave1-demo"))
        ).scalar_one()
        company = (
            await session.execute(select(Company).where(Company.name == "Wave 1 Demo LLC"))
        ).scalar_one()
        site = (await session.execute(select(Site).where(Site.name == "Wave 1 Site"))).scalar_one()
        department = (
            await session.execute(select(Department).where(Department.code == "DEMO-PROD"))
        ).scalar_one()
        position = (
            await session.execute(select(Position).where(Position.name == "Мастер участка"))
        ).scalar_one()
        person = (
            await session.execute(select(Person).where(Person.personnel_number == "D-001"))
        ).scalar_one()
        course = (
            await session.execute(select(TrainingCourse).where(TrainingCourse.code == "demo-intro"))
        ).scalar_one()

        assert company.tenant_id == tenant.id
        assert site.tenant_id == tenant.id
        assert department.tenant_id == tenant.id
        assert position.tenant_id == tenant.id
        assert person.tenant_id == tenant.id
        assert course.tenant_id == tenant.id


@pytest.mark.anyio
async def test_async_session_local_ensures_explicit_schema_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensured: list[tuple[str, str | None, bool]] = []

    monkeypatch.setattr(db_session, "_SUPPORTS_SCHEMAS", True)
    monkeypatch.setattr(db_session, "ensure_shared_schema", lambda *, implicit=False: None)
    monkeypatch.setattr(
        db_session,
        "ensure_tenant_schema",
        lambda slug, *, schema_name=None, implicit=False: ensured.append(
            (slug, schema_name, implicit)
        ),
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
        lambda slug, *, schema_name=None, implicit=False: ensured.append(
            (slug, schema_name, implicit)
        ),
    )

    tenant = await api_dependencies._fetch_tenant_by_identifier("schema-demo")

    assert tenant.slug == "schema-demo"
    assert tenant.schema_name == "tenant_schema_demo"
    assert ensured == [("schema-demo", "tenant_schema_demo", True)]


def test_ensure_tenant_schema_skips_implicit_bootstrap_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_ensure_tenant_schema_allows_explicit_bootstrap_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    async def _record_ensure(slug, *, schema_name=None):
        ensured.append((slug, schema_name))

    monkeypatch.setattr(
        "app.services.tenants.bootstrap.service.aensure_tenant_schema",
        _record_ensure,
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


@pytest.mark.anyio
async def test_per_request_search_path_switching_between_tenants(
    sessionmaker,
) -> None:
    """Regression test for TZ-2.1-MVP-02: per-request search_path switching.

    Each new session for a different tenant must have the correct search_path set.
    This validates that search_path is properly applied on session entry and
    correctly switches between consecutive requests to different tenants.
    """
    # Get reference tenants (the test fixture seeds "test", "acme", and others).
    async with sessionmaker() as seed:
        test_tenant = (await seed.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        acme_tenant = (await seed.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()

    # First request: open session for "test" tenant
    async with db_session.AsyncSessionLocal(tenant="test") as session_a:
        # Validate session info has correct search path
        search_path_a = session_a.info.get("search_path")
        tenant_a = session_a.info.get("tenant")
        assert tenant_a == "test"
        assert search_path_a is not None
        assert isinstance(search_path_a, list)
        # search_path should include tenant_test schema and public
        assert len(search_path_a) >= 1
        assert "public" in search_path_a or len(search_path_a) == 1

        # Verify tenant ID is set correctly
        tenant_id_a = session_a.info.get("tenant_id")
        assert tenant_id_a == test_tenant.id

    # Second request: open session for "acme" tenant
    async with db_session.AsyncSessionLocal(tenant="acme") as session_b:
        # Validate session info has DIFFERENT search path
        search_path_b = session_b.info.get("search_path")
        tenant_b = session_b.info.get("tenant")
        assert tenant_b == "acme"
        assert search_path_b is not None
        assert isinstance(search_path_b, list)
        # search_path differs per tenant only on PostgreSQL (schema-per-tenant).
        # SQLite has no schemas, so both tenants resolve to ['public']; tenant
        # switching is still validated below via tenant_id.
        if search_path_a != ["public"]:
            assert search_path_b != search_path_a

        # Verify tenant ID changed
        tenant_id_b = session_b.info.get("tenant_id")
        assert tenant_id_b == acme_tenant.id
        assert tenant_id_b != tenant_id_a

    # Third request: verify switching back to "test" restores original search_path
    async with db_session.AsyncSessionLocal(tenant="test") as session_c:
        search_path_c = session_c.info.get("search_path")
        tenant_c = session_c.info.get("tenant")
        assert tenant_c == "test"
        # search_path should match the first session (same tenant)
        assert search_path_c == search_path_a
        assert session_c.info.get("tenant_id") == test_tenant.id
