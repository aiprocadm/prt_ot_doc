"""SEC-67: symmetric encryption for secrets stored at rest (webhook HMAC secrets).

Passwords and API tokens are one-way *hashed* elsewhere; webhook HMAC secrets must
survive round-trip (they sign outbound payloads), so they need reversible encryption
rather than a hash. This module encrypts them with AES-256-GCM.

Storage formats
---------------

* ``enc:v2:<kid>:<base64(nonce[12] || ciphertext || tag)>`` — current. The key id is
  stored WITH the ciphertext, which is what makes rotation possible without downtime:
  old rows keep naming the key that can still decrypt them while new writes already
  use the new key.
* ``enc:v1:<base64(...)>`` — legacy, no key id. Decrypted with the key registered as
  ``v1`` (i.e. ``APP_SECRET_ENCRYPTION_KEY``). Never produced any more.
* anything without a prefix — legacy plaintext, returned verbatim, so a value keeps
  working without a backfill.

Rotation (разд. 67.2 «сменить ключ шифрования без простоя»)
-----------------------------------------------------------

1. add the new key to the keyring alongside the old one and point
   ``APP_SECRET_ENCRYPTION_ACTIVE_KID`` at it — new writes use it, old rows still
   decrypt with the retired key;
2. run ``scripts/rotate_secret_keys.py`` to re-encrypt stored secrets onto the active
   key (idempotent; ``--check`` only reports);
3. once nothing references the retired kid, drop it from the keyring.

Configuration
-------------

* ``APP_SECRET_ENCRYPTION_KEYS`` — keyring, ``kid:key`` pairs separated by commas or
  whitespace (``2026a:BASE64…,2026b:BASE64…``).
* ``APP_SECRET_ENCRYPTION_ACTIVE_KID`` — which kid new writes use. Defaults to the
  single configured key, so a one-key setup needs no extra configuration.
* ``APP_SECRET_ENCRYPTION_KEY`` — the pre-rotation single key; keeps working and is
  registered under the kid ``v1``.

Keys are base64, hex, or an arbitrary passphrase (hashed to 32 bytes). Required in
production/staging — encryption without a configured key is meaningless, so it fails
closed. In development/test a deterministic key is derived from ``SECRET_KEY``.

External KMS/Vault stays out of the application: the keyring is exactly what a secret
manager would inject, and the ``kid`` carried by every value is what lets a
KMS-managed key be retired.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX_V1 = "enc:v1:"
_PREFIX_V2 = "enc:v2:"
_ANY_PREFIX = (_PREFIX_V1, _PREFIX_V2)
_NONCE_BYTES = 12
_KEY_BYTES = 32
_DEV_KEY_SALT = b"webhook-secret-v1"
_LEGACY_KID = "v1"
# Kid лежит в открытом виде внутри значения — держим его безопасным для парсинга и логов.
_KID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


class SecretDecryptError(ValueError):
    """Raised when a prefixed secret cannot be decrypted (bad key or corruption)."""


class SecretKeyringError(RuntimeError):
    """Raised when the configured keyring is unusable (missing/duplicate/bad kid)."""


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


def _dev_key(settings) -> bytes:
    seed = (getattr(settings, "secret_key", "") or "dev-secret").encode("utf-8")
    return hashlib.sha256(seed + _DEV_KEY_SALT).digest()


def _parse_keyring(raw: str) -> dict[str, bytes]:
    """Parse ``kid:key`` pairs. Insertion order is preserved (first = default active)."""

    keyring: dict[str, bytes] = {}
    for chunk in re.split(r"[,\s]+", (raw or "").strip()):
        if not chunk:
            continue
        kid, sep, key_part = chunk.partition(":")
        if not sep:
            raise SecretKeyringError(
                f"APP_SECRET_ENCRYPTION_KEYS entry {chunk!r} must be 'kid:key'"
            )
        kid = kid.strip()
        if not _KID_RE.match(kid):
            raise SecretKeyringError(f"invalid key id {kid!r} (allowed: A-Za-z0-9._-, <=32)")
        if kid in keyring:
            raise SecretKeyringError(f"duplicate key id {kid!r} in APP_SECRET_ENCRYPTION_KEYS")
        decoded = _decode_key(key_part)
        if decoded is None:
            raise SecretKeyringError(f"empty key for key id {kid!r}")
        keyring[kid] = decoded
    return keyring


def load_keyring(settings=None) -> tuple[dict[str, bytes], str]:
    """Return ``(keyring, active_kid)``.

    Fails closed in production/staging when nothing is configured: falling back there
    to a key derived from ``SECRET_KEY`` would mean every deployment that forgot the
    variable encrypts under a guessable key.
    """

    settings = settings or _settings()
    keyring = _parse_keyring(getattr(settings, "secret_encryption_keys", "") or "")

    legacy = _decode_key(getattr(settings, "secret_encryption_key", "") or "")
    if legacy is not None:
        # Явная запись v1 в keyring приоритетнее устаревшей одиночной переменной.
        keyring.setdefault(_LEGACY_KID, legacy)

    if not keyring:
        if getattr(settings, "app_env", "development") in ("production", "staging"):
            raise SecretKeyringError(
                "APP_SECRET_ENCRYPTION_KEY or APP_SECRET_ENCRYPTION_KEYS is required to "
                "encrypt secrets in production/staging"
            )
        keyring = {_LEGACY_KID: _dev_key(settings)}

    active = (getattr(settings, "secret_encryption_active_kid", "") or "").strip()
    if active:
        if active not in keyring:
            raise SecretKeyringError(
                f"APP_SECRET_ENCRYPTION_ACTIVE_KID={active!r} is not in the keyring "
                f"(known: {sorted(keyring)})"
            )
    else:
        # Без явного выбора активен единственный/первый ключ: требовать ACTIVE_KID
        # при одном ключе значило бы сломать существующие развёртывания.
        active = next(iter(keyring))
    return keyring, active


def active_key_id(settings=None) -> str:
    return load_keyring(settings)[1]


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_ANY_PREFIX)


def key_id_of(stored: str | None) -> str | None:
    """Key id a stored value was encrypted with, or ``None`` for plaintext.

    Lets the rotation script tell «already on the active key» from «still on a retired
    one» without decrypting anything.
    """

    if not isinstance(stored, str):
        return None
    if stored.startswith(_PREFIX_V1):
        return _LEGACY_KID
    if stored.startswith(_PREFIX_V2):
        kid = stored[len(_PREFIX_V2) :].split(":", 1)[0]
        return kid or None
    return None


def encrypt_secret(plaintext: str, *, settings=None) -> str:
    """Encrypt ``plaintext`` with the ACTIVE key into the ``enc:v2:<kid>:`` envelope."""

    keyring, kid = load_keyring(settings)
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(keyring[kid]).encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"{_PREFIX_V2}{kid}:" + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(stored: str | None, *, settings=None) -> str | None:
    """Decrypt a stored secret.

    Non-prefixed values are returned verbatim (legacy plaintext); ``None`` stays
    ``None``. A value naming a key id that is no longer in the keyring raises:
    returning the ciphertext instead would silently produce signatures that no
    subscriber can verify.
    """

    if stored is None:
        return None
    if not is_encrypted(stored):
        return stored

    keyring, _active = load_keyring(settings)
    if stored.startswith(_PREFIX_V1):
        kid, payload = _LEGACY_KID, stored[len(_PREFIX_V1) :]
    else:
        kid, _sep, payload = stored[len(_PREFIX_V2) :].partition(":")

    key = keyring.get(kid)
    if key is None:
        raise SecretDecryptError(
            f"secret was encrypted with key id {kid!r}, which is not in the keyring "
            f"(known: {sorted(keyring)}) — restore the retired key before rotating"
        )
    try:
        blob = base64.b64decode(payload)
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except (InvalidTag, binascii.Error, ValueError) as exc:
        raise SecretDecryptError("failed to decrypt secret") from exc


def reencrypt_secret(stored: str | None, *, settings=None) -> str | None:
    """Re-encrypt a stored value onto the active key. Idempotent.

    Returns the value unchanged when it is already on the active key, so the rotation
    script skips writes instead of rewriting every row on every run.
    """

    if stored is None:
        return None
    _keyring, active = load_keyring(settings)
    if stored.startswith(_PREFIX_V2) and key_id_of(stored) == active:
        return stored
    plaintext = decrypt_secret(stored, settings=settings)
    if plaintext is None:  # pragma: no cover - guarded by the None check above
        return None
    return encrypt_secret(plaintext, settings=settings)
