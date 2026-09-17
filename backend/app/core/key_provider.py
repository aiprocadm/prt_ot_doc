"""Откуда берётся связка ключей шифрования (SEC-67, разд. 67 Доп. №3).

ЧТО БЫЛО. Связка ключей читалась ровно из одного места — переменных окружения
``APP_SECRET_ENCRYPTION_KEYS`` / ``APP_SECRET_ENCRYPTION_KEY``. Строка матрицы
SEC-67 честно писала: «Осталось: только KMS/Vault (внешняя система)». Это
означало, что подключение хранилища ключей — РАЗРАБОТКА, а не настройка: кто-то
должен был прийти и переписать чтение ключей.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Хранилище ключей нельзя купить
кодом, но можно сделать так, чтобы его подключение стало настройкой. Здесь
заведён шов: связку отдаёт ПРОВАЙДЕР, и провайдеров два.

* ``env`` — прежнее поведение, переменные окружения. Умолчание: существующие
  развёртывания не замечают изменения.
* ``command`` — связку отдаёт внешняя команда. Так устроено большинство
  хранилищ: агент Vault, CLI облачного KMS, sops, скрипт развёртывания. Команда
  печатает JSON в стандартный вывод::

      {"keys": "v2:<base64>,v1:<base64>", "active_kid": "v2"}

  ``active_kid`` необязателен: без него активен первый ключ связки.

ПОЧЕМУ НЕ БИБЛИОТЕКА КОНКРЕТНОГО ОБЛАКА. Выбор облака — решение владельца,
которое ещё не принято, а зависимость от SDK одного поставщика пришлось бы
выкорчёвывать при смене. Команда — общий знаменатель: любое хранилище умеет
отдать секрет в CLI. Цена — один процесс на обновление связки (раз в TTL).

ГРОМКАЯ ОШИБКА ВМЕСТО ТИХОГО ОТКАТА. Если команда упала, не уложилась в срок
или напечатала мусор — это ошибка, а не повод молча взять ключи из окружения.
Тихий откат означал бы, что при недоступном хранилище приложение начинает
шифровать другим ключом, и половина значений перестаёт читаться. Отказ громкий:
``KeyProviderError``.

ЧЕГО ЗДЕСЬ НАМЕРЕННО НЕТ. Вывод команды не попадает ни в журнал, ни в текст
ошибки: это сами ключи. В сообщении об ошибке — только код возврата и то, что
команда напечатала в поток ошибок.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass

#: Сколько секунд связка живёт в памяти, прежде чем спросить хранилище заново.
#: Ноль отключает кэш (нужно тестам и ручной проверке).
DEFAULT_TTL_SECONDS = 300.0

#: Сколько ждём внешнюю команду. Хранилище ключей, которое думает дольше
#: десяти секунд, всё равно не годится на путь запроса.
DEFAULT_TIMEOUT_SECONDS = 10.0

ENV_PROVIDER = "env"
COMMAND_PROVIDER = "command"
KNOWN_PROVIDERS = (ENV_PROVIDER, COMMAND_PROVIDER)


class KeyProviderError(RuntimeError):
    """Связку ключей не удалось получить у настроенного провайдера."""


@dataclass(frozen=True)
class KeyMaterial:
    """Связка в том же виде, в каком её понимает ``secret_cipher``.

    ``keys`` — строка пар ``kid:key`` через запятую (формат
    ``APP_SECRET_ENCRYPTION_KEYS``), ``legacy_key`` — одиночный ключ прежнего
    формата, ``active_kid`` — какой ключ использовать для новых записей.
    Пустые строки означают «не задано», а не «пустой ключ».
    """

    keys: str = ""
    legacy_key: str = ""
    active_kid: str = ""


_CACHE_LOCK = threading.Lock()
#: (материал, момент получения, отпечаток настроек) — чтобы смена настроек в
#: тестах и на перезапуске не подхватывала чужой кэш.
_CACHED: tuple[KeyMaterial, float, tuple[str, str]] | None = None


def reset_cache() -> None:
    """Забыть закэшированную связку (тесты, ручная проверка ротации)."""

    global _CACHED
    with _CACHE_LOCK:
        _CACHED = None


def _provider_name(settings) -> str:
    raw = (getattr(settings, "secret_key_provider", "") or ENV_PROVIDER).strip().lower()
    if raw not in KNOWN_PROVIDERS:
        raise KeyProviderError(
            f"APP_SECRET_KEY_PROVIDER={raw!r} is unknown (known: {', '.join(KNOWN_PROVIDERS)})"
        )
    return raw


def _env_material(settings) -> KeyMaterial:
    return KeyMaterial(
        keys=(getattr(settings, "secret_encryption_keys", "") or ""),
        legacy_key=(getattr(settings, "secret_encryption_key", "") or ""),
        active_kid=(getattr(settings, "secret_encryption_active_kid", "") or ""),
    )


def _command_material(settings) -> KeyMaterial:
    command = (getattr(settings, "secret_key_command", "") or "").strip()
    if not command:
        raise KeyProviderError(
            "APP_SECRET_KEY_PROVIDER=command requires APP_SECRET_KEY_COMMAND "
            '(a command printing {"keys": "kid:key,..."} to stdout)'
        )
    timeout = float(
        getattr(settings, "secret_key_command_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        or DEFAULT_TIMEOUT_SECONDS
    )
    try:
        completed = subprocess.run(  # noqa: S603 - команда задаётся администратором
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise KeyProviderError(f"APP_SECRET_KEY_COMMAND is not executable: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise KeyProviderError(
            f"APP_SECRET_KEY_COMMAND did not answer within {timeout:g}s"
        ) from exc

    if completed.returncode != 0:
        # Печатаем только поток ошибок: стандартный вывод — это ключи.
        stderr = (completed.stderr or "").strip()[:500]
        raise KeyProviderError(
            f"APP_SECRET_KEY_COMMAND exited with code {completed.returncode}"
            + (f": {stderr}" if stderr else "")
        )

    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        raise KeyProviderError(
            "APP_SECRET_KEY_COMMAND must print JSON with a 'keys' field "
            f"(parse failed at position {exc.pos})"
        ) from exc

    if not isinstance(payload, dict):
        raise KeyProviderError("APP_SECRET_KEY_COMMAND must print a JSON object")

    keys = str(payload.get("keys") or "").strip()
    legacy = str(payload.get("key") or "").strip()
    if not keys and not legacy:
        raise KeyProviderError("APP_SECRET_KEY_COMMAND printed no keys (expected 'keys' or 'key')")
    return KeyMaterial(
        keys=keys,
        legacy_key=legacy,
        active_kid=str(payload.get("active_kid") or "").strip(),
    )


def _fingerprint(settings, provider: str) -> tuple[str, str]:
    """Отпечаток настроек провайдера: меняется — кэш недействителен."""

    if provider == COMMAND_PROVIDER:
        return (provider, (getattr(settings, "secret_key_command", "") or "").strip())
    return (provider, "")


def get_key_material(settings) -> KeyMaterial:
    """Связка ключей от настроенного провайдера (с кэшем на TTL).

    Кэшируется только успех: неудачу кэшировать нельзя, иначе одна недоступность
    хранилища гасила бы приложение на весь TTL уже после того, как хранилище
    вернулось.
    """

    global _CACHED
    provider = _provider_name(settings)
    if provider == ENV_PROVIDER:
        # Переменные окружения читаются даром и меняются только с перезапуском:
        # кэш здесь ничего не экономит, а в тестах мешал бы.
        return _env_material(settings)

    ttl = float(
        getattr(settings, "secret_key_provider_ttl_seconds", DEFAULT_TTL_SECONDS)
        if getattr(settings, "secret_key_provider_ttl_seconds", None) is not None
        else DEFAULT_TTL_SECONDS
    )
    print_key = _fingerprint(settings, provider)
    now = time.monotonic()

    with _CACHE_LOCK:
        cached = _CACHED
        if cached is not None and ttl > 0:
            material, fetched_at, fingerprint = cached
            if fingerprint == print_key and (now - fetched_at) < ttl:
                return material

    material = _command_material(settings)

    with _CACHE_LOCK:
        _CACHED = (material, time.monotonic(), print_key)
    return material


__all__ = [
    "COMMAND_PROVIDER",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_TTL_SECONDS",
    "ENV_PROVIDER",
    "KNOWN_PROVIDERS",
    "KeyMaterial",
    "KeyProviderError",
    "get_key_material",
    "reset_cache",
]
