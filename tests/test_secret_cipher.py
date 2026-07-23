"""Unit tests for SEC-67 secret encryption (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.secret_cipher import (
    SecretDecryptError,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
)

_DEV = SimpleNamespace(secret_encryption_key="", app_env="test", secret_key="unit-secret")


def test_round_trip() -> None:
    enc = encrypt_secret("hunter2", settings=_DEV)
    assert is_encrypted(enc)
    assert enc.startswith("enc:v1:")
    assert enc != "hunter2"
    assert decrypt_secret(enc, settings=_DEV) == "hunter2"


def test_legacy_plaintext_passthrough() -> None:
    # Pre-existing unencrypted secrets must keep working (no forced backfill).
    assert decrypt_secret("plain-legacy-secret", settings=_DEV) == "plain-legacy-secret"
    assert not is_encrypted("plain-legacy-secret")


def test_none_stays_none() -> None:
    assert decrypt_secret(None, settings=_DEV) is None
    assert not is_encrypted(None)


def test_nonce_is_randomized() -> None:
    assert encrypt_secret("x", settings=_DEV) != encrypt_secret("x", settings=_DEV)


def test_corrupted_ciphertext_raises() -> None:
    with pytest.raises(SecretDecryptError):
        decrypt_secret("enc:v1:bm90LXZhbGlkLWJsb2I=", settings=_DEV)


def test_wrong_key_raises() -> None:
    enc = encrypt_secret("topsecret", settings=_DEV)
    other = SimpleNamespace(secret_encryption_key="", app_env="test", secret_key="different")
    with pytest.raises(SecretDecryptError):
        decrypt_secret(enc, settings=other)


def test_configured_key_used_over_dev_key() -> None:
    key32 = "A" * 43 + "="  # 32 bytes base64
    cfg = SimpleNamespace(secret_encryption_key=key32, app_env="production", secret_key="")
    enc = encrypt_secret("prodsecret", settings=cfg)
    assert decrypt_secret(enc, settings=cfg) == "prodsecret"


def test_production_without_key_fails_closed() -> None:
    cfg = SimpleNamespace(secret_encryption_key="", app_env="production", secret_key="s")
    with pytest.raises(RuntimeError):
        encrypt_secret("x", settings=cfg)


def test_development_without_key_works() -> None:
    cfg = SimpleNamespace(secret_encryption_key="", app_env="development", secret_key="devkey")
    assert decrypt_secret(encrypt_secret("y", settings=cfg), settings=cfg) == "y"
