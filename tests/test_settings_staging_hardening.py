"""Staging/production must not start with documented dev defaults for infra secrets.

Settings fields are populated via their env-var aliases (UPPERCASE). ``model_validate``
honours ``validation_alias`` only, so these payloads MUST use the alias keys —
lowercase field names silently fall back to defaults (app_env -> "development"),
which would skip every staging validator and make the assertions inert.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core import config
from app.core.config import DEV_PRIVATE_KEY, DEV_PUBLIC_KEY, Settings, SettingsError

_SAFE_STAGING_PRIVATE_KEY, _SAFE_STAGING_PUBLIC_KEY = config._generate_dev_keypair()


@pytest.fixture(autouse=True)
def _isolate_app_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Constructor kwargs must not be overridden by ambient env in dev shells."""
    for key in (
        "APP_ENV",
        "SECRET_KEY",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_BACKEND",
        "POSTGRES_PASSWORD",
        "PRIVATE_KEY_PEM",
        "PUBLIC_KEY_PEM",
    ):
        monkeypatch.delenv(key, raising=False)
    config.reset_settings_cache()
    yield
    config.reset_settings_cache()


_STAGING_SAFE_BASE: dict[str, object] = {
    "APP_ENV": "staging",
    "PRIVATE_KEY_PEM": _SAFE_STAGING_PRIVATE_KEY,
    "PUBLIC_KEY_PEM": _SAFE_STAGING_PUBLIC_KEY,
    "POSTGRES_PASSWORD": "staging-postgres-secret-not-default",
    "S3_ACCESS_KEY": "staging-access-not-prt-local",
    "S3_SECRET_KEY": "staging-secret-not-prt-local",
    "S3_BACKEND": "minio",
    "INBOUND_WEBHOOK_HMAC_SECRET": "staging-hmac-secret",
}


def test_staging_rejects_default_secret_key() -> None:
    with pytest.raises(SettingsError, match="Staging configuration must override"):
        Settings.model_validate({
            **_STAGING_SAFE_BASE,
            "SECRET_KEY": "change-me",
        })


def test_staging_rejects_default_s3_credentials_when_other_secrets_ok() -> None:
    with pytest.raises(SettingsError, match="Staging configuration must override"):
        Settings.model_validate({
            "APP_ENV": "staging",
            "SECRET_KEY": "not-the-default-staging-secret-key-32chars!!",
            "PRIVATE_KEY_PEM": _SAFE_STAGING_PRIVATE_KEY,
            "PUBLIC_KEY_PEM": _SAFE_STAGING_PUBLIC_KEY,
            "POSTGRES_PASSWORD": "staging-postgres-secret-not-default",
            "S3_ACCESS_KEY": "prt_local_access",
            "S3_SECRET_KEY": "prt_local_secret",
            "S3_BACKEND": "minio",
            "INBOUND_WEBHOOK_HMAC_SECRET": "staging-hmac-secret",
        })


def test_staging_requires_inbound_webhook_hmac_secret() -> None:
    with pytest.raises(SettingsError, match="Staging configuration must override"):
        Settings.model_validate({
            **_STAGING_SAFE_BASE,
            "SECRET_KEY": "not-the-default-staging-secret-key-32chars!!",
            "INBOUND_WEBHOOK_HMAC_SECRET": "",
        })


def test_staging_rejects_bundled_dev_jwt_keypair() -> None:
    with pytest.raises(SettingsError, match="must not use bundled development JWT key pair"):
        Settings.model_validate({
            "APP_ENV": "staging",
            "SECRET_KEY": "not-the-default-staging-secret-key-32chars!!",
            "PRIVATE_KEY_PEM": DEV_PRIVATE_KEY,
            "PUBLIC_KEY_PEM": DEV_PUBLIC_KEY,
            "POSTGRES_PASSWORD": "staging-postgres-secret-not-default",
            "S3_ACCESS_KEY": "staging-access-not-prt-local",
            "S3_SECRET_KEY": "staging-secret-not-prt-local",
            "S3_BACKEND": "minio",
            "INBOUND_WEBHOOK_HMAC_SECRET": "staging-hmac-secret",
        })
