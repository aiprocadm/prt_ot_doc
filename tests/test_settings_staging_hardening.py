"""Staging/production must not start with documented dev defaults for infra secrets."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core import config
from app.core.config import DEV_PRIVATE_KEY, DEV_PUBLIC_KEY, Settings, SettingsError


@pytest.fixture(autouse=True)
def _isolate_app_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Constructor kwargs must not be overridden by ambient APP_ENV in dev shells."""
    monkeypatch.delenv("APP_ENV", raising=False)
    config.reset_settings_cache()
    yield
    config.reset_settings_cache()


_STAGING_SAFE_BASE: dict[str, object] = {
    "app_env": "staging",
    "jwt_private_key_pem": DEV_PRIVATE_KEY,
    "jwt_public_key_pem": DEV_PUBLIC_KEY,
    "postgres_password": "staging-postgres-secret-not-default",
    "s3_access_key": "staging-access-not-prt-local",
    "s3_secret_key": "staging-secret-not-prt-local",
    "s3_backend": "minio",
}


def test_staging_rejects_default_secret_key() -> None:
    with pytest.raises(SettingsError, match="Staging configuration must override"):
        Settings(
            **_STAGING_SAFE_BASE,
            secret_key="change-me",
        )


def test_staging_rejects_default_s3_credentials_when_other_secrets_ok() -> None:
    with pytest.raises(SettingsError, match="Staging configuration must override"):
        Settings(
            app_env="staging",
            secret_key="not-the-default-staging-secret-key-32chars!!",
            jwt_private_key_pem=DEV_PRIVATE_KEY,
            jwt_public_key_pem=DEV_PUBLIC_KEY,
            postgres_password="staging-postgres-secret-not-default",
            s3_access_key="prt_local_access",
            s3_secret_key="prt_local_secret",
            s3_backend="minio",
        )
