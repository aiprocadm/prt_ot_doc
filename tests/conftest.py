from __future__ import annotations

import os
import sys
import tempfile
import types
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

# Set environment variables BEFORE any app imports
os.environ.setdefault("APP_NAME", "TestService")
os.environ["APP_TRUSTED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ.setdefault("DEFAULT_LOCALE", "en-US")
os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)
os.environ["ENABLE_METRICS"] = "true"
_DEFAULT_SQLITE_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "prt_ot_doc_tests.db")
_SQLITE_TEST_DB = f"sqlite+aiosqlite:///{_DEFAULT_SQLITE_TEST_DB_PATH}"
os.environ.setdefault("DATABASE_URL", _SQLITE_TEST_DB)
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("REDIS_RESULT_URL", "cache+memory://")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")

# Some CI/python environments don't provide the stdlib `crypt` module
# (e.g. Windows, slim containers). Passlib imports it during auth setup,
# so provide a tiny fallback stub for tests when it's unavailable.
sys.modules.setdefault("crypt", types.SimpleNamespace(crypt=lambda secret, salt: "mocked"))

import typer.core as _typer_core
from click.core import UNSET as _CLICK_UNSET
try:
    from click.core import UNSET as _CLICK_UNSET
except ImportError:  # Click versions without UNSET symbol.
    _CLICK_UNSET = object()

# Typer 0.9.0 / Click 8.1.x compatibility fixes:
#
# 1. TyperArgument.make_metavar: Click 8.1 added a required `ctx` param but
#    Typer 0.9.0 still overrides it with only (self). Patch it to accept ctx and
#    call get_metavar with the correct (param, ctx) signature.
def _patched_make_metavar(self, ctx=None, *args: object, **kwargs: object) -> str:
    if self.metavar is not None:
        return self.metavar
    var = (self.name or "").upper()
    if not self.required:
        var = "[{}]".format(var)
    type_var = self.type.get_metavar(param=self, ctx=ctx)
    if type_var:
        var += f":{type_var}"
    if self.nargs != 1:
        var += "..."
    return var


_typer_core.TyperArgument.make_metavar = _patched_make_metavar  # type: ignore[method-assign]

# 2. TyperOption.__init__: Typer 0.9.0 passes flag_value=None to Click. In
#    Click 8.1, the UNSET sentinel (not None) signals "not set", so None is
#    treated as an explicit flag value and triggers is_flag=True for ALL options.
#    Fix: replace flag_value=None with UNSET when the caller did not mean a flag.
_orig_typer_option_init = _typer_core.TyperOption.__init__


def _patched_typer_option_init(self, *, flag_value=None, is_flag=None, **kwargs):  # type: ignore[no-untyped-def]
    if flag_value is None:
        flag_value = _CLICK_UNSET
    _orig_typer_option_init(self, flag_value=flag_value, is_flag=is_flag, **kwargs)


_typer_core.TyperOption.__init__ = _patched_typer_option_init  # type: ignore[method-assign]

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import create_app
from app.api.dependencies import get_session, get_tenant_record
from app.core.security import issue_access_token
from app.core.tenant import TENANT_HEADER, tenant_required
from app.db import Base, SharedBase
from app.db.session import AsyncSessionLocal, configure_engine
from app.domains.files import s3
from app.models.models import Company, RoleEnum, Tenant, User
from app.services.clamav import reset_quarantine_publisher
from app.services.file_storage import FileStorageService
from tests.utils.factories import TestDataFactory

configure_engine(database_url=os.environ["DATABASE_URL"], echo=False)


@pytest.fixture()
def anyio_backend() -> str:
    """Force AnyIO to use asyncio for the entire test suite."""

    return "asyncio"


def _prepare_sqlite_metadata() -> None:
    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in Base.metadata.tables:
        Tenant.__table__.to_metadata(Base.metadata, schema=None)


@pytest.fixture(autouse=True)
def _reset_storage() -> None:
    """Keep the in-memory storage clean between tests."""

    storage = FileStorageService.default()
    storage.clear()
    reset_quarantine_publisher()
    yield
    storage.clear()
    reset_quarantine_publisher()


@pytest_asyncio.fixture()
async def app_fixture():
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_USER", "test")
    os.environ.setdefault("POSTGRES_PASSWORD", "test")
    os.environ.setdefault("POSTGRES_DB", "test")

    _prepare_sqlite_metadata()
    db_fd, db_file = tempfile.mkstemp(prefix="prt_ot_doc_tests_", suffix=".db")
    os.close(db_fd)
    sqlite_url = f"sqlite+aiosqlite:///{db_file}"
    configure_engine(database_url=sqlite_url, echo=False)
    engine = create_async_engine(
        sqlite_url,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)

    TestSession = async_sessionmaker(bind=engine, expire_on_commit=False)

    seed_tenants = {"test", "acme", "beta", "gamma", "delta", "zeta", "epsilon"}

    async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as shared_session:
        shared_existing = set((await shared_session.execute(select(Tenant.slug))).scalars().all())
        for slug in seed_tenants:
            if slug in shared_existing:
                continue
            shared_session.add(
                Tenant(
                    slug=slug,
                    name=slug.title(),
                    contact_email=f"{slug}@example.com",
                )
            )
        await shared_session.commit()
        shared_tenants = {
            tenant.slug: tenant
            for tenant in (await shared_session.execute(select(Tenant))).scalars().all()
            if tenant.slug in seed_tenants
        }

    async with TestSession() as seed_session:
        existing_slugs = set((await seed_session.execute(select(Tenant.slug))).scalars().all())
        for slug in seed_tenants:
            if slug in existing_slugs:
                continue
            shared = shared_tenants.get(slug)
            seed_session.add(
                Tenant(
                    id=(shared.id if shared is not None else None),
                    slug=slug,
                    name=(shared.name if shared is not None else slug.title()),
                    contact_email=(shared.contact_email if shared is not None else f"{slug}@example.com"),
                )
            )
        await seed_session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.state.test_sessionmaker = TestSession

    class _StubRedisClient:
        def __init__(self) -> None:
            self.lengths: dict[str, int] = {}

        async def ping(self) -> bool:
            return True

        async def llen(self, key: str) -> int:
            return self.lengths.get(key, 0)

        async def close(self) -> None:
            return None

    app.state.redis_client = _StubRedisClient()

    async def override_tenant_record(request: Request) -> Tenant:
        preloaded = getattr(request.state, "tenant_record", None)
        if isinstance(preloaded, Tenant):
            return preloaded

        tenant_slug = request.headers.get(TENANT_HEADER) or request.headers.get("x-tenant-slug")
        if not tenant_slug and request.url.path.startswith(("/api/v1/auth", "/api/v1/portal")):
            tenant_slug = "test"
        info = tenant_required(tenant_slug)
        async with TestSession() as session:
            filters = [Tenant.slug == info.slug, Tenant.code == info.slug]
            if len(info.slug) == 36:
                filters.append(Tenant.id == str(UUID(info.slug)))
            tenant = (await session.execute(select(Tenant).where(or_(*filters)))).scalar_one_or_none()
            if tenant is None or not tenant.is_active:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
            return tenant

    app.dependency_overrides[get_tenant_record] = override_tenant_record

    yield app

    await engine.dispose()
    if os.path.exists(db_file):
        os.remove(db_file)


@pytest_asyncio.fixture()
async def async_client(app_fixture):
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture()
def sessionmaker(app_fixture):
    return app_fixture.state.test_sessionmaker


@pytest.fixture()
def data_factory(sessionmaker) -> TestDataFactory:
    """Provide a test data factory bound to the tenant-aware session maker."""

    return TestDataFactory(sessionmaker)


@pytest.fixture()
def aws() -> None:
    moto = pytest.importorskip("moto", reason="moto is required for S3 integration tests")
    with moto.mock_aws():
        s3.ensure_bucket()
        yield


@pytest_asyncio.fixture()
async def make_auth_headers(
    sessionmaker, data_factory: TestDataFactory
) -> Callable[[RoleEnum], Awaitable[dict[str, str]]]:
    async def factory(
        role: RoleEnum = RoleEnum.ADMIN,
        *,
        email: str | None = None,
        company_id: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, str]:
        candidate_email = email or f"{role.value}-api@example.com"
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            result = await session.execute(select(User).where(User.email == candidate_email))
            user = result.scalar_one_or_none()
            if user is None:
                user = await data_factory.create_user(
                    tenant=tenant,
                    email=candidate_email,
                    role=role,
                    session=session,
                )

            company_claim: str | None = None
            if role in {RoleEnum.CLIENT_ADMIN, RoleEnum.CLIENT_USER}:
                company_record: Company | None = None
                if company_id:
                    company_record = await session.get(Company, company_id)
                    if company_record is not None and company_record.tenant_id != tenant.id:
                        company_record = None
                if company_record is None:
                    generated_name = (company_name or f"{role.value.title()} Co")[:255]
                    company_record = await data_factory.create_company(
                        tenant=tenant,
                        name=generated_name,
                        session=session,
                    )
                if user.company_id != company_record.id:
                    user.company_id = company_record.id
                company_claim = str(company_record.id)

            await session.commit()
            await session.refresh(user)
            user_id = user.id
            token_tenant_id = user.tenant_id
            company_claim = company_claim or (
                str(user.company_id) if getattr(user, "company_id", None) else None
            )

        request_tenant_id = str(tenant.id)
        async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as public_session:
            public_tenant = (
                await public_session.execute(select(Tenant).where(Tenant.slug == tenant.slug))
            ).scalar_one_or_none()
            if public_tenant is not None:
                request_tenant_id = str(public_tenant.id)

        claims: dict[str, str | object] = {"tenant_id": request_tenant_id}
        if company_claim:
            claims["company_id"] = company_claim

        token = issue_access_token(
            subject=user_id,
            tenant=tenant.slug,
            role=role.value,
            additional_claims=claims,
        )

        return {"Authorization": f"Bearer {token}", "x-tenant": request_tenant_id}

    return factory
