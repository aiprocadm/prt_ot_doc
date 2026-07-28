"""Unit tests for SEC-67 secret encryption (no DB)."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from app.core.secret_cipher import (
    SecretDecryptError,
    SecretKeyringError,
    active_key_id,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
    key_id_of,
    reencrypt_secret,
)

_DEV = SimpleNamespace(secret_encryption_key="", app_env="test", secret_key="unit-secret")


def test_round_trip() -> None:
    enc = encrypt_secret("hunter2", settings=_DEV)
    assert is_encrypted(enc)
    # SEC-67: формат несёт key id — без него ротация без простоя невозможна.
    assert enc.startswith("enc:v2:v1:")
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


# --- SEC-67: ротация ключа без простоя (разд. 67.2) ---------------------------------

_KEY_A = base64.b64encode(b"A" * 32).decode()
_KEY_B = base64.b64encode(b"B" * 32).decode()


def _keyring_settings(keys: str, active: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        secret_encryption_key="",
        secret_encryption_keys=keys,
        secret_encryption_active_kid=active,
        app_env="test",
        secret_key="unit-secret",
    )


def test_rotation_keeps_old_values_readable() -> None:
    """Суть ротации без простоя: новые записи на новом ключе, старые ещё читаются."""

    before = _keyring_settings(f"old:{_KEY_A}")
    old_value = encrypt_secret("hunter2", settings=before)
    assert key_id_of(old_value) == "old"

    after = _keyring_settings(f"old:{_KEY_A},new:{_KEY_B}", active="new")
    assert active_key_id(after) == "new"
    # Старое значение читается ретайрд-ключом...
    assert decrypt_secret(old_value, settings=after) == "hunter2"
    # ...а новые записи уже на новом.
    assert key_id_of(encrypt_secret("fresh", settings=after)) == "new"


def test_reencrypt_moves_value_to_active_key_and_is_idempotent() -> None:
    before = _keyring_settings(f"old:{_KEY_A}")
    old_value = encrypt_secret("hunter2", settings=before)

    after = _keyring_settings(f"old:{_KEY_A},new:{_KEY_B}", active="new")
    rotated = reencrypt_secret(old_value, settings=after)

    assert key_id_of(rotated) == "new"
    assert decrypt_secret(rotated, settings=after) == "hunter2"
    # Повторный прогон скрипта ротации не должен переписывать строку заново.
    assert reencrypt_secret(rotated, settings=after) is rotated


def test_legacy_v1_format_still_decrypts() -> None:
    """Значения, записанные до ротации (без key id), обязаны читаться."""

    legacy_settings = SimpleNamespace(
        secret_encryption_key=_KEY_A, app_env="test", secret_key="unit-secret"
    )
    # Собираем v1-значение тем же ключом, что зарегистрирован под kid "v1".
    v2 = encrypt_secret("hunter2", settings=legacy_settings)
    body = v2[len("enc:v2:v1:") :]
    v1 = "enc:v1:" + body

    assert key_id_of(v1) == "v1"
    assert decrypt_secret(v1, settings=legacy_settings) == "hunter2"


def test_retired_key_removed_too_early_fails_loudly() -> None:
    """Молчаливый возврат шифротекста дал бы подписи, которые никто не проверит."""

    before = _keyring_settings(f"old:{_KEY_A}")
    old_value = encrypt_secret("hunter2", settings=before)

    only_new = _keyring_settings(f"new:{_KEY_B}", active="new")
    with pytest.raises(SecretDecryptError) as excinfo:
        decrypt_secret(old_value, settings=only_new)
    assert "old" in str(excinfo.value)


def test_active_kid_must_exist_in_keyring() -> None:
    with pytest.raises(SecretKeyringError):
        active_key_id(_keyring_settings(f"old:{_KEY_A}", active="missing"))


def test_malformed_keyring_is_rejected() -> None:
    with pytest.raises(SecretKeyringError):
        active_key_id(_keyring_settings("no-colon-here"))
    with pytest.raises(SecretKeyringError):
        active_key_id(_keyring_settings(f"dup:{_KEY_A},dup:{_KEY_B}"))


def test_single_key_setup_needs_no_active_kid() -> None:
    """Существующие развёртывания с одним ключом не должны требовать новой переменной."""

    assert active_key_id(_keyring_settings(f"only:{_KEY_A}")) == "only"


def test_key_id_of_plaintext_is_none() -> None:
    assert key_id_of("plain") is None
    assert key_id_of(None) is None
