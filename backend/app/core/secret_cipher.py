"""SEC-67: symmetric encryption for secrets stored at rest (webhook HMAC secrets).

Passwords and API tokens are one-way *hashed* elsewhere; webhook HMAC secrets must
survive round-trip (they sign outbound payloads), so they need reversible encryption
rather than a hash. This module encrypts them with AES-256-GCM.

Storage formats
---------------

* ``enc:v3:<kid>:<base64(nonce[12] || ciphertext || tag)>`` — current. Same envelope as
  v2, but the AES key is DERIVED PER TENANT from the keyring key (see below).
* ``enc:v2:<kid>:<base64(...)>`` — previous. One shared key per kid for every tenant.
  Still decrypted; never produced any more.
* ``enc:v1:<base64(...)>`` — legacy, no key id. Decrypted with the key registered as
  ``v1`` (i.e. ``APP_SECRET_ENCRYPTION_KEY``). Never produced any more.
* anything without a prefix — legacy plaintext, returned verbatim, so a value keeps
  working without a backfill.

Per-tenant key isolation (разд. 67.2)
-------------------------------------

ТЗ: «компрометация ключа одного арендатора не раскрывает других». Until v3 every
tenant's secrets were encrypted with the SAME key, so one leaked key opened the whole
platform — and a ciphertext copied from one tenant's row into another's decrypted
happily, which is a cross-tenant transplant that RLS cannot see.

v3 derives a separate key per scope with HKDF-SHA256 over the keyring key, using the
scope as ``info``. Consequences worth stating plainly:

* a derived key that leaks (extracted from a process serving one tenant, a dump of one
  row's key material) opens ONLY that tenant;
* a ciphertext moved to another tenant no longer decrypts — the key differs, so the
  GCM tag fails. That turns a silent data mix-up into a loud error;
* the MASTER key still opens everything. Derivation contains the blast radius of a
  derived key, not of the keyring itself — that is what «где возможно» in the spec
  means, and pretending otherwise would be worse than not writing it down.

Global rows (a webhook subscription with ``tenant_id IS NULL``) use the scope
``__global__``: they are legitimately platform-wide, and inventing a tenant for them
would make their secrets undecryptable.

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
_PREFIX_V3 = "enc:v3:"
_ANY_PREFIX = (_PREFIX_V1, _PREFIX_V2, _PREFIX_V3)
_NONCE_BYTES = 12
_KEY_BYTES = 32
_DEV_KEY_SALT = b"webhook-secret-v1"
_LEGACY_KID = "v1"
#: Соль вывода per-tenant ключей. Меняется только вместе с версией формата:
#: смена соли делает НЕЧИТАЕМЫМИ все ранее записанные значения.
_HKDF_SALT = b"ptd-secret-scope-v3"
#: Область для строк, у которых арендатора нет по существу (глобальные подписки).
GLOBAL_SCOPE = "__global__"
# Kid лежит в открытом виде внутри значения — держим его безопасным для парсинга и логов.
_KID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


class SecretDecryptError(ValueError):
    """Raised when a prefixed secret cannot be decrypted (bad key or corruption)."""


class SecretKeyringError(RuntimeError):
    """Raised when the configured keyring is unusable (missing/duplicate/bad kid)."""


def _settings():
    from app.core.config import get_settings

    return get_settings()


def _scope(tenant_id: str | None) -> str:
    """Область ключа: арендатор или ``__global__``.

    Пустая строка и ``None`` — одно и то же: строка без арендатора. Разводить их
    значило бы получить два разных ключа для одних и тех же данных, и половина
    значений перестала бы читаться после безобидного рефакторинга.
    """

    value = (tenant_id or "").strip()
    return value or GLOBAL_SCOPE


def _derive(master: bytes, tenant_id: str | None) -> bytes:
    """Ключ арендатора из ключа связки (HKDF-SHA256, разд. 67.2)."""

    from cryptography.hazmat.primitives import hashes  # noqa: PLC0415 - тяжёлый импорт
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: PLC0415

    return HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=_HKDF_SALT,
        info=_scope(tenant_id).encode("utf-8"),
    ).derive(master)


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

    from app.core.key_provider import get_key_material  # noqa: PLC0415 - цикл импорта

    settings = settings or _settings()
    # SEC-67 (2026-09-14): связку отдаёт провайдер — окружение или внешнее
    # хранилище ключей. Ошибка провайдера намеренно НЕ гасится: молчаливый откат
    # на окружение означал бы шифрование другим ключом при недоступном KMS.
    material = get_key_material(settings)
    keyring = _parse_keyring(material.keys)

    legacy = _decode_key(material.legacy_key)
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

    active = material.active_kid.strip()
    if active:
        if active not in keyring:
            raise SecretKeyringError(
                f"active key id {active!r} is not in the keyring "
                f"(known: {sorted(keyring)}); source: APP_SECRET_ENCRYPTION_ACTIVE_KID "
                "or the 'active_kid' field returned by APP_SECRET_KEY_COMMAND"
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
    for prefix in (_PREFIX_V2, _PREFIX_V3):
        if stored.startswith(prefix):
            kid = stored[len(prefix) :].split(":", 1)[0]
            return kid or None
    return None


def encrypt_secret(plaintext: str, *, tenant_id: str | None, settings=None) -> str:
    """Encrypt ``plaintext`` for ONE tenant into the ``enc:v3:<kid>:`` envelope.

    ``tenant_id`` is keyword-ONLY and has no default on purpose: a default would let a
    call site quietly encrypt под чужой областью, и обнаружилось бы это только тем,
    что секрет перестал расшифровываться. ``None`` разрешён и означает «строка
    платформенная» (глобальная подписка) — но это надо написать явно.
    """

    keyring, kid = load_keyring(settings)
    nonce = os.urandom(_NONCE_BYTES)
    key = _derive(keyring[kid], tenant_id)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"{_PREFIX_V3}{kid}:" + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(stored: str | None, *, tenant_id: str | None, settings=None) -> str | None:
    """Decrypt a stored secret.

    Non-prefixed values are returned verbatim (legacy plaintext); ``None`` stays
    ``None``. A value naming a key id that is no longer in the keyring raises:
    returning the ciphertext instead would silently produce signatures that no
    subscriber can verify.

    ``enc:v1``/``enc:v2`` читаются общим ключом связки (как и раньше), ``enc:v3`` —
    ключом, выведенным для ``tenant_id``. Значение, перенесённое в чужого арендатора,
    на v3 не расшифруется — это не поломка, а ровно та защита, ради которой формат
    и введён.
    """

    if stored is None:
        return None
    if not is_encrypted(stored):
        return stored

    keyring, _active = load_keyring(settings)
    per_tenant = stored.startswith(_PREFIX_V3)
    if stored.startswith(_PREFIX_V1):
        kid, payload = _LEGACY_KID, stored[len(_PREFIX_V1) :]
    else:
        prefix = _PREFIX_V3 if per_tenant else _PREFIX_V2
        kid, _sep, payload = stored[len(prefix) :].partition(":")

    key = keyring.get(kid)
    if key is None:
        raise SecretDecryptError(
            f"secret was encrypted with key id {kid!r}, which is not in the keyring "
            f"(known: {sorted(keyring)}) — restore the retired key before rotating"
        )
    if per_tenant:
        key = _derive(key, tenant_id)
    try:
        blob = base64.b64decode(payload)
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except (InvalidTag, binascii.Error, ValueError) as exc:
        raise SecretDecryptError("failed to decrypt secret") from exc


def reencrypt_secret(stored: str | None, *, tenant_id: str | None, settings=None) -> str | None:
    """Re-encrypt a stored value onto the active key AND the current format. Idempotent.

    Возвращает значение без изменений, только если оно уже на активном ключе И в
    формате v3 — иначе прогон ротации оставил бы общий ключ v2 навсегда: он ведь
    «на активном kid», и старая проверка сочла бы его свежим.
    """

    if stored is None:
        return None
    _keyring, active = load_keyring(settings)
    if stored.startswith(_PREFIX_V3) and key_id_of(stored) == active:
        return stored
    plaintext = decrypt_secret(stored, tenant_id=tenant_id, settings=settings)
    if plaintext is None:  # pragma: no cover - guarded by the None check above
        return None
    return encrypt_secret(plaintext, tenant_id=tenant_id, settings=settings)
