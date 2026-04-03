"""Staging/production must not start with documented dev defaults."""

from __future__ import annotations

import pytest

from app.core.config import DEV_PRIVATE_KEY, DEV_PUBLIC_KEY, Settings, SettingsError

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


def test_staging_requires_explicit_jwt_keys() -> None:
    with pytest.raises(SettingsError, match="PRIVATE_KEY_PEM and PUBLIC_KEY_PEM"):
        Settings(
            app_env="staging",
            secret_key="not-the-default-staging-secret-key-32chars!!",
            postgres_password="staging-postgres-secret-not-default",
            s3_access_key="staging-access-not-prt-local",
            s3_secret_key="staging-secret-not-prt-local",
            s3_backend="minio",
            jwt_private_key_pem="",
            jwt_public_key_pem="",
        )
