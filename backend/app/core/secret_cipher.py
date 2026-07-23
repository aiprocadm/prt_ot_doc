"""SEC-67: symmetric encryption for secrets stored at rest (webhook HMAC secrets).

Passwords and API tokens are one-way *hashed* elsewhere; webhook HMAC secrets must
survive round-trip (they sign outbound payloads), so they need reversible encryption
rather than a hash. This module encrypts them with AES-256-GCM under a master key.

Storage format: ``enc:v1:<base64(nonce[12] || ciphertext || tag)>``. ``decrypt_secret``
returns anything WITHOUT the prefix verbatim, so pre-existing plaintext secrets keep
working and no backfill migration is required — values are encrypted lazily as they are
created or rotated.

Master key: env ``APP_SECRET_ENCRYPTION_KEY`` (base64 or hex, 32 bytes). Required in
production/staging (encryption without a configured key is meaningless → fail-closed).
In development/test a deterministic key is derived from ``SECRET_KEY`` so local runs and
the suite work without extra configuration (mirrors the bundled dev RSA key for JWT).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "enc:v1:"
_NONCE_BYTES = 12
_KEY_BYTES = 32
_DEV_KEY_SALT = b"webhook-secret-v1"


class SecretDecryptError(ValueError):
    """Raised when a prefixed secret cannot be decrypted (bad key or corruption)."""


def _settings():
    from app.core.config import get_settings

    return get_settings()


def _decode_key(raw: str) -> bytes | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            key = decoder(raw)
        except (binascii.Error, ValueError):
            continue
        if len(key) == _KEY_BYTES:
            return key
    # Fallback: derive 32 bytes from an arbitrary-length passphrase.
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _master_key(settings=None) -> bytes:
    settings = settings or _settings()
    configured = _decode_key(getattr(settings, "secret_encryption_key", "") or "")
    if configured is not None:
        return configured
    if getattr(settings, "app_env", "development") in ("production", "staging"):
        raise RuntimeError(
            "APP_SECRET_ENCRYPTION_KEY is required to encrypt secrets in " "production/staging"
        )
    # Deterministic development/test key derived from SECRET_KEY.
    seed = (getattr(settings, "secret_key", "") or "dev-secret").encode("utf-8")
    return hashlib.sha256(seed + _DEV_KEY_SALT).digest()


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_secret(plaintext: str, *, settings=None) -> str:
    """Encrypt ``plaintext`` into the ``enc:v1:`` envelope."""
    key = _master_key(settings)
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(stored: str | None, *, settings=None) -> str | None:
    """Decrypt a stored secret. Non-prefixed values are returned verbatim (legacy
    plaintext); ``None`` stays ``None``."""
    if stored is None:
        return None
    if not is_encrypted(stored):
        return stored
    key = _master_key(settings)
    try:
        blob = base64.b64decode(stored[len(_PREFIX) :])
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except (InvalidTag, binascii.Error, ValueError) as exc:
        raise SecretDecryptError("failed to decrypt secret") from exc
