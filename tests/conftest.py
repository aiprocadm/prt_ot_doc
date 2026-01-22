from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from fastapi import Header, HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import create_app
from app.api.dependencies import get_session, get_tenant_record
from app.core.tenant import TENANT_HEADER, tenant_required
from app.db import Base, SharedBase
from app.db.session import configure_engine
from app.core.security import issue_access_token
from app.models.models import Company, RoleEnum, Tenant, User
from app.services.clamav import reset_quarantine_publisher
from app.services.file_storage import FileStorageService
from tests.utils.factories import TestDataFactory

os.environ.setdefault("APP_NAME", "TestService")
os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

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
        Tenant.__table__.tometadata(Base.metadata, schema=None)


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
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)

    TestSession = async_sessionmaker(bind=engine, expire_on_commit=False)

    seed_tenants = {"test", "acme", "beta", "gamma", "delta", "zeta", "epsilon"}

    async with TestSession() as seed_session:
        for slug in seed_tenants:
            seed_session.add(
                Tenant(
                    slug=slug,
                    name=slug.title(),
                    contact_email=f"{slug}@example.com",
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

    async def override_tenant_record(
        tenant_slug: str | None = Header(default=None, alias=TENANT_HEADER)
    ) -> Tenant:
        info = tenant_required(tenant_slug)
        async with TestSession() as session:
            tenant = (
                await session.execute(
                    select(Tenant).where(Tenant.slug == info.slug)
                )
            ).scalar_one_or_none()
            if tenant is None or not tenant.is_active:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
            return tenant

    app.dependency_overrides[get_tenant_record] = override_tenant_record

    yield app

    await engine.dispose()


@pytest_asyncio.fixture()
async def async_client(app_fixture):
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"x-tenant-slug": "test"},
    ) as client:
        yield client


@pytest.fixture()
def sessionmaker(app_fixture):
    return app_fixture.state.test_sessionmaker


@pytest.fixture()
def data_factory(sessionmaker) -> TestDataFactory:
    """Provide a test data factory bound to the tenant-aware session maker."""

    return TestDataFactory(sessionmaker)


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

        claims: dict[str, str | object] = {"tenant_id": token_tenant_id}
        if company_claim:
            claims["company_id"] = company_claim

        token = issue_access_token(
            subject=user_id,
            tenant=tenant.slug,
            role=role.value,
            additional_claims=claims,
        )
        return {"Authorization": f"Bearer {token}"}

    return factory
