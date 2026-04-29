import pytest
from httpx import AsyncClient
from moto import mock_aws
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.error_handlers import TRACE_HEADER
from app.core.config import get_settings
from app.core.rate_limit import (
    configure_rate_limiter,
    limiter,
    login_per_identity,
    upload_per_tenant,
)
from app.domains.files import s3
from app.models.models import RoleEnum, Tenant, User
from app.services.auth import hash_password


@pytest.fixture(autouse=True)
def _force_asyncio_backend(anyio_backend_name: str) -> None:
    if anyio_backend_name != "asyncio":
        pytest.skip("asyncio backend only")


@pytest.fixture(autouse=True)
def _configure_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_IDENTITY", "2/minute")
    monkeypatch.setenv("RATE_LIMIT_UPLOAD_PER_TENANT", "2/minute")
    settings = get_settings(force_reload=True)
    limiter.reset()
    configure_rate_limiter(settings)
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]
    configure_rate_limiter(get_settings())
    limiter.reset()


@pytest.fixture()
def configure_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ENDPOINT", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_SECURE", "false")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s3.reset_client_cache()
    s3.ensure_bucket()
    yield
    s3.reset_client_cache()


@pytest.fixture()
def aws() -> None:
    with mock_aws():
        yield


@pytest.mark.anyio("asyncio")
async def test_login_rate_limit(
    async_client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    assert login_per_identity() == "2/minute"
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        user = User(
            tenant_id=tenant.id,
            email="ratelimit@example.com",
            full_name="Limiter",
            role=RoleEnum.ADMIN,
            hashed_password=hash_password("secret"),
        )
        session.add(user)
        await session.commit()

    payload = {"email": "ratelimit@example.com", "password": "secret"}
    login_headers = {"x-tenant": tenant.slug}

    # Two successful requests (within limit of 2/minute)
    response = await async_client.post("/api/v1/auth/login", json=payload, headers=login_headers)
    assert response.status_code == 200
    response = await async_client.post("/api/v1/auth/login", json=payload, headers=login_headers)
    assert response.status_code == 200

    # Third request should be rate limited
    limited = await async_client.post("/api/v1/auth/login", json=payload, headers=login_headers)
    assert limited.status_code == 429
    body = limited.json()
    assert body["code"] == "RATE_LIMIT_EXCEEDED"
    expected_message = login_per_identity().replace("/", " per 1 ")
    assert body["message"] == expected_message
    assert isinstance(body.get("details"), dict)
    assert body["trace_id"]
    header_trace = limited.headers.get(TRACE_HEADER, "")
    assert body["trace_id"] in {value.strip() for value in header_trace.split(",") if value.strip()}


@pytest.mark.anyio("asyncio")
@pytest.mark.usefixtures("aws", "configure_storage")
async def test_upload_rate_limit(
    async_client: AsyncClient, make_auth_headers
) -> None:
    payload = b"throttle"
    headers = {**dict(async_client.headers), **await make_auth_headers(email="uploader@example.com")}

    assert upload_per_tenant() == "2/minute"

    for _ in range(2):
        response = await async_client.post(
            "/api/v1/files-legacy/upload",
            files={"file": ("sample.txt", payload, "text/plain")},
            headers=headers,
        )
        assert response.status_code == 201

    limited = await async_client.post(
        "/api/v1/files-legacy/upload",
        files={"file": ("sample.txt", payload, "text/plain")},
        headers=headers,
    )
    assert limited.status_code == 429
    body = limited.json()
    assert body["code"] == "RATE_LIMIT_EXCEEDED"
    expected_message = upload_per_tenant().replace("/", " per 1 ")
    assert body["message"] == expected_message
    assert isinstance(body.get("details"), dict)
    assert body["trace_id"]
    header_trace = limited.headers.get(TRACE_HEADER, "")
    assert body["trace_id"] in {value.strip() for value in header_trace.split(",") if value.strip()}
