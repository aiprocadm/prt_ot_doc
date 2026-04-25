"""OpenAPI/Swagger URL alignment, tenant middleware bypass, production policy."""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.core.config import Settings

_TEST_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA5Qf9DcYv+zlt6fJkD2ol0X+m6IjfHybZQkW8fvl65mQrkfRZ
TXf8RBJ7fFkAB1f6v+V9RGUi6i9n0xIcdb14j5rVmM6bgjNe6Qv7qiAaNfQdlWsL
f8TX4A50ymQ0dn03G7f7LiiQNP9Fma9Evp+sIZXnX60LJIV9P/l8Ekv1fo6E0uB7
2f8Q0s9UjheU2X6w3k3sXj/Fx2M8RDNq4j1WgP3xE6xE6W2q3lclhA8Bf3SxV+2w
Rh6lVtq8y2U2g0JfNn+2m1JzF1QWmH5VQXn4Vx6oxU2zj7Yq7f1n0B+4v/7m8s6b
U6fN0zRr2b0uGZxXx3dV7GfXkS6e7Qv8J7m2hwIDAQABAoIBAQCEzA3qK8z3G1mU
gOZ3m9J9w6tqCzA5XStR6Gk3fW6rJj7v0Y3L9n2mU9R2QkQ6n7v3QY8mQ+eB2J3z
6Bf7lQxjG8m8x7Qx8j6U2a8vS4H7QfQ+K5m8f3l7j4QbX1D2w7t8n3h6j5k4l3m2
1n0b9v8c7x6z5y4w3v2u1t0s9r8q7p6o5n4m3l2k1j0h9g8f7e6d5c4b3a2Z1Y0X
WvUtSrJq8m8v6n5b4c3d2e1f0g9h8j7k6l5m4n3b2v1c0x9z8y7w6v5u4t3s2r1q
p0o9n8m7l6k5j4h3g2f1e0d9c8b7a6Z5Y4X3W2V1U0T9AoGBAPf8qM2gYh0iY3sY
3S4l7k9n1m2b4v6c8x0z2a4d6f8h0j2l4n6p8r0t2v4x6z8B0D2F4H6J8L0N2P4R
6T8V0X2Z4b6d8f0h2j4l6n8p0r2t4v6x8z0B2D4F6H8J0L2N4P6R8T0V2X4Z6b8d
e0f2h4j6l8n0p2r4t6v8x0z2AoGBAP2n1m0l9k8j7h6g5f4d3s2a1q0w9e8r7t6y
5u4i3o2p1a0s9d8f7g6h5j4k3l2z1x0c9v8b7n6m5q4w3e2r1t0y9u8i7o6p5a4s
3d2f1g0h9j8k7l6z5x4c3v2b1n0m9q8w7e6r5t4y3u2i1o0p9a8s7d6f5g4h3j2k
1l0z9x8c7v6b5n4m3q2w1e0r9t8y7u6AoGBAI2f4h6j8k0l2z4x6c8v0b2n4m6q8
w0e2r4t6y8u0i2o4p6a8s0d2f4g6h8j0k2l4z6x8c0v2b4n6m8q0w2e4r6t8y0u2
i4o6p8a0s2d4f6g8h0j2k4l6z8x0c2v4b6n8m0q2w4e6r8t0y2u4i6o8p0a2s4d6
f8g0h2j4k6l8z0x2c4v6b8n0m2q4w6e8AoGBAK9x7c5v3b1n0m2q4w6e8r0t2y4u
6i8o0p2a4s6d8f0g2h4j6k8l0z2x4c6v8b0n2m4q6w8e0r2t4y6u8i0o2p4a6s8d
0f2g4h6j8k0l2z4x6c8v0b2n4m6q8w0e2r4t6y8u0i2o4p6a8s0d2f4g6h8j0k2l4
z6x8c0v2b4n6m8q0w2e4r6t8y0u2i4oAoGAB8f6d4s2a0q9w8e7r6t5y4u3i2o1p0
a9s8d7f6g5h4j3k2l1z0x9c8v7b6n5m4q3w2e1r0t9y8u7i6o5p4a3s2d1f0g9h8
j7k6l5z4x3c2v1b0n9m8q7w6e5r4t3y2u1i0o9p8a7s6d5f4g3h2j1k0l9z8x7c6
v5b4n3m2q1w0e9r8t7y6u5i4o3p2a1s0d9f8g7h6j5k4l3z2x1
-----END RSA PRIVATE KEY-----"""

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
async def test_production_create_app_exposes_no_openapi_routes(monkeypatch: pytest.MonkeyPatch) -> None:
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
