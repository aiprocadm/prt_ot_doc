"""OpenAPI/Swagger URL alignment, tenant middleware bypass, production policy."""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.core.config import Settings

_TEST_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAtgrj+IOar1FSpKyxfsNNIeHLqdJ9Wh56YfeV+OcsHdHcaP0b
9KuUL6o0e1RQ47Z3dIB6LCWv+ciBj//BUCCdQJcM12/p5466Xr8Bee/YihOGIgLX
OZV4ykgkCMSm6zoShRvo/+qy/VF+b+Qi39Jmk/sgnPemehK69I5+i9Q2UUHFaI1s
Xph/2vJq1UCDK3jQvwiY74OP6nW12fX/ScHaRQ5HGjo52idwvHUgaWDabo17d7nB
2h5Mrc1N2QskfoLnDu/PKF/dmGl/RDDezdiTwCQz5hdBWRw9IhqaHoJKEsFyJH3b
byJkWvK+lmcK80oysO9CafgRzUwRctP83MkKvwIDAQABAoIBADdBaf4SUD7707Z5
VqzV8fchVtTWt8bFbodTA9oXrSvl+d2CSlyDQgkPxDtVFfJwfaTGpI7G57nNMwp2
6oH8TE8BKlwwM5LeH1LH7lZJR3Rtxa6IJzTq2k2oBQwGSNYoe9ucY6ZeYnMCq/qh
iDZg4lLzjGwovYbbLZUytVWTFeOmrE0UVvlKkNv9XJSZ+42ptT32nQzM1dnVHsnr
OwysO2tq/I2hadbvlAB5UJXr2viAICj8egYO7bYCQjpMXUxzzH4gwNEnATg6ZwxV
uCKolZr6KgtxVb65DFJKC+LZ9eWxwQ0BLumrbFrRquArP3w52H9KbBqy+/K7Kkht
KkHpBiUCgYEA5YHYoY51CwZGv2KXdShfrdflbigsRmLLOLAtWtgCmUkIuAA1NiPt
mR16//qVTIoT5NENsQiRQ0Syx15Zv0m8LezWhAwq1e6zCtyxH/C7y9BWAlr0AGAi
CJyhKFMcZdwUVMcmxVFfuPmzRv0GYQvSreap+QJVXLtcmmQey5dKEeUCgYEAyw5r
Lg1OH0aZOIoevCFPx7JlGiV5V/Kb8fhBqhoAXuP2yRn7PaGn16IZpiJO1yvg2UEH
l1OiFLDyN00LeMue+jn2Jf2CkX7F7SPKdTpXHrgd+CBWh1I3AUdHhdH9L0cH74wK
FbMscoIE28S4KMGEklVKeW/8jTExc5nUpHFyb9MCgYEAk26aLw5IedCKWh+HlCdf
b1mldOIxrvV//uaN/DGPWdDk3O6lQCZMV3Pss8vRZN2+cdsppHQQfNoAzrn5hTxk
ukvOcf0u90bjlTK4RgBrYz5uQg0TebpHoqibjj/1mimKlftpGJBxoW4mkI+yLV1e
9X+b6O5qz6s8jaGLdtW1K1ECgYAMT0p2Fz5mLPx67fyhAQ/6FjmE1UK+7yk/CQLK
Eht1pTI/zMBrYxJuwxf09116M+HEqemQ5fQMdxGoApawcv+nQb5HXU/+DAZpsuLC
KpA/f3/pm+RC/dvxyuVuGmXT6OV1QzMVT7BhHLq4q/tSFTE5QcxrAjv4P0Q1Mt0u
PuZmGwKBgDkPDlOgZpp2vzHC1sGVgqnSGtieej+3Y/OGJtZdzg44c5YxlAeF15D0
El1hUA2v97l0+pvR+YCAU2nJQEktCbxYxcrFr3IOhAHGxLSsw8j6xbnmc/eRGXU0
Hv2uxRHtzy0j2K2XaT9xbeG+m5JTe5wK8u8Cbm/PexJtcHIOXC1o
-----END RSA PRIVATE KEY-----
"""

_TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtgrj+IOar1FSpKyxfsNN
IeHLqdJ9Wh56YfeV+OcsHdHcaP0b9KuUL6o0e1RQ47Z3dIB6LCWv+ciBj//BUCCd
QJcM12/p5466Xr8Bee/YihOGIgLXOZV4ykgkCMSm6zoShRvo/+qy/VF+b+Qi39Jm
k/sgnPemehK69I5+i9Q2UUHFaI1sXph/2vJq1UCDK3jQvwiY74OP6nW12fX/ScHa
RQ5HGjo52idwvHUgaWDabo17d7nB2h5Mrc1N2QskfoLnDu/PKF/dmGl/RDDezdiT
wCQz5hdBWRw9IhqaHoJKEsFyJH3bbyJkWvK+lmcK80oysO9CafgRzUwRctP83MkK
vwIDAQAB
-----END PUBLIC KEY-----
"""

_TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5Qf9DcYv+zlt6fJkD2ol
0X+m6IjfHybZQkW8fvl65mQrkfRZTXf8RBJ7fFkAB1f6v+V9RGUi6i9n0xIcdb14
j5rVmM6bgjNe6Qv7qiAaNfQdlWsLf8TX4A50ymQ0dn03G7f7LiiQNP9Fma9Evp+s
IZXnX60LJIV9P/l8Ekv1fo6E0uB72f8Q0s9UjheU2X6w3k3sXj/Fx2M8RDNq4j1W
gP3xE6xE6W2q3lclhA8Bf3SxV+2wRh6lVtq8y2U2g0JfNn+2m1JzF1QWmH5VQXn4
Vx6oxU2zj7Yq7f1n0B+4v/7m8s6bU6fN0zRr2b0uGZxXx3dV7GfXkS6e7Qv8J7m2
hwIDAQAB
-----END PUBLIC KEY-----"""

_PRODUCTION_LIKE: dict[str, object] = {
    "APP_ENV": "production",
    "SECRET_KEY": "not-the-default-staging-secret-key-32chars!!",
    "POSTGRES_PASSWORD": "staging-postgres-secret-not-default",
    "S3_ACCESS_KEY": "staging-access-not-prt-local",
    "S3_SECRET_KEY": "staging-secret-not-prt-local",
    "S3_BACKEND": "minio",
    "PRIVATE_KEY_PEM": _TEST_PRIVATE_KEY,
    "PUBLIC_KEY_PEM": _TEST_PUBLIC_KEY,
    "INBOUND_WEBHOOK_HMAC_SECRET": "test-webhook-secret-not-default-value",
    "LIBREOFFICE_BIN": sys.executable,
    "ENABLE_OPENAPI_DOCS": True,
    "ENABLE_METRICS": False,
}


def test_production_disables_openapi_docs_even_when_env_requests_true() -> None:
    settings = Settings.model_validate(_PRODUCTION_LIKE)
    assert settings.enable_openapi_docs is False


@pytest.mark.anyio
async def test_production_create_app_exposes_no_openapi_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_validate(_PRODUCTION_LIKE)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    app = create_app(settings)
    assert app.docs_url is None
    assert app.openapi_url is None
    assert app.redoc_url is None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs = await client.get("/api/docs")
        assert docs.status_code == 404
        spec = await client.get("/api/openapi.json")
        assert spec.status_code == 404


@pytest.mark.anyio
async def test_openapi_ui_reachable_without_x_tenant_when_docs_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "API_PREFIX": "/api",
            "SECRET_KEY": "test-secret-key-32chars-minimum!!",
            "LIBREOFFICE_BIN": sys.executable,
            "ENABLE_OPENAPI_DOCS": True,
            "ENABLE_METRICS": False,
        }
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    app = create_app(settings)
    assert app.docs_url == "/api/docs"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs = await client.get("/api/docs")
        assert docs.status_code == 200
        spec = await client.get("/api/openapi.json")
        assert spec.status_code == 200
