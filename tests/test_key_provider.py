"""Сторож: связку ключей можно взять из внешнего хранилища (SEC-67, 2026-09-14).

ЧТО БЫЛО. Ключи читались только из переменных окружения, и строка матрицы
SEC-67 честно писала «осталось KMS/Vault (внешняя система)». То есть
подключение хранилища было разработкой, а не настройкой.

ЧТО ПРОВЕРЯЕТСЯ ЗДЕСЬ. Что шов настоящий: связка приходит из внешней команды,
ротация подхватывается, а любая неудача хранилища — ГРОМКАЯ. Последнее важнее
всего: молчаливый откат на окружение при недоступном KMS означал бы, что
приложение начинает шифровать другим ключом, и прежние значения перестают
читаться. Такую поломку заметили бы недели спустя, по нечитаемым подписям
вебхуков.

КАК ЗАПУСТИТЬ: ``PYTHONPATH=backend pytest tests/test_key_provider.py -v``.
"""

from __future__ import annotations

import base64
import json
import os
import stat
import sys
from types import SimpleNamespace

import pytest

from app.core.key_provider import (
    KeyProviderError,
    get_key_material,
    reset_cache,
)
from app.core.secret_cipher import decrypt_secret, encrypt_secret, load_keyring

_KEY_A = base64.b64encode(b"A" * 32).decode()
_KEY_B = base64.b64encode(b"B" * 32).decode()


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    yield
    reset_cache()


def _env_settings(**over) -> SimpleNamespace:
    base = {
        "secret_key_provider": "env",
        "secret_encryption_keys": "",
        "secret_encryption_key": "",
        "secret_encryption_active_kid": "",
        "secret_key_command": "",
        "secret_key_provider_ttl_seconds": 0.0,
        "app_env": "test",
        "secret_key": "unit-secret",
    }
    base.update(over)
    return SimpleNamespace(**base)


def _script(tmp_path, body: str, name: str = "keys.py"):
    """Файл-команда, печатающая то, что просят. Возвращает строку команды."""

    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return f"{sys.executable} {path}"


def test_env_provider_is_the_default_and_unchanged() -> None:
    """Умолчание не меняется: существующие развёртывания ничего не замечают."""

    settings = _env_settings(secret_encryption_keys=f"v2:{_KEY_A}")
    material = get_key_material(settings)
    assert material.keys == f"v2:{_KEY_A}"
    keyring, active = load_keyring(settings)
    assert active == "v2"
    assert sorted(keyring) == ["v2"]


def test_command_provider_supplies_the_keyring(tmp_path) -> None:
    """Связка приходит из внешней команды — так устроены агент Vault и CLI KMS."""

    payload = json.dumps({"keys": f"kms1:{_KEY_A},old:{_KEY_B}", "active_kid": "kms1"})
    command = _script(tmp_path, f"print({payload!r})")
    settings = _env_settings(secret_key_provider="command", secret_key_command=command)

    keyring, active = load_keyring(settings)
    assert active == "kms1"
    assert sorted(keyring) == ["kms1", "old"]

    # Шифрование/расшифровка идут теми же ключами — шов не декоративный.
    stored = encrypt_secret("hunter2", tenant_id="t-1", settings=settings)
    assert decrypt_secret(stored, tenant_id="t-1", settings=settings) == "hunter2"


def test_command_failure_is_loud_and_never_falls_back_to_env(tmp_path) -> None:
    """Главная проверка строки: недоступное хранилище НЕ подменяется окружением.

    Если бы здесь был тихий откат, приложение при упавшем KMS продолжило бы
    работать — но уже на другом ключе, и прежние значения стали бы нечитаемы.
    """

    command = _script(tmp_path, "import sys\nsys.stderr.write('vault sealed')\nsys.exit(3)")
    settings = _env_settings(
        secret_key_provider="command",
        secret_key_command=command,
        # В окружении лежит вполне рабочая связка — соблазн откатиться максимальный.
        secret_encryption_keys=f"v1:{_KEY_B}",
    )
    with pytest.raises(KeyProviderError) as err:
        load_keyring(settings)
    assert "code 3" in str(err.value)
    assert "vault sealed" in str(err.value)


def test_command_output_is_not_leaked_into_the_error(tmp_path) -> None:
    """Стандартный вывод команды — это ключи; в тексте ошибки его быть не должно."""

    command = _script(tmp_path, f"print({_KEY_A!r})")  # не JSON
    settings = _env_settings(secret_key_provider="command", secret_key_command=command)
    with pytest.raises(KeyProviderError) as err:
        get_key_material(settings)
    assert _KEY_A not in str(err.value)
    assert "must print JSON" in str(err.value)


def test_command_that_prints_nothing_is_an_error(tmp_path) -> None:
    command = _script(tmp_path, "print('{}')")
    settings = _env_settings(secret_key_provider="command", secret_key_command=command)
    with pytest.raises(KeyProviderError, match="printed no keys"):
        get_key_material(settings)


def test_command_provider_without_command_is_an_error() -> None:
    settings = _env_settings(secret_key_provider="command", secret_key_command="")
    with pytest.raises(KeyProviderError, match="APP_SECRET_KEY_COMMAND"):
        get_key_material(settings)


def test_unknown_provider_is_an_error() -> None:
    """Опечатка в имени провайдера не должна тихо означать «окружение»."""

    settings = _env_settings(secret_key_provider="vaultt")
    with pytest.raises(KeyProviderError, match="unknown"):
        get_key_material(settings)


def test_keyring_is_cached_for_ttl_then_refetched(tmp_path) -> None:
    """Хранилище не спрашивают на каждый запрос, но ротацию оно подхватывает."""

    counter = tmp_path / "calls.txt"
    body = (
        "import json, pathlib\n"
        f"p = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) + 1 if p.exists() else 1\n"
        "p.write_text(str(n))\n"
        f"print(json.dumps({{'keys': 'k%d:{_KEY_A}' % n}}))\n"
    )
    command = _script(tmp_path, body)
    settings = _env_settings(
        secret_key_provider="command",
        secret_key_command=command,
        secret_key_provider_ttl_seconds=60.0,
    )

    first = get_key_material(settings)
    second = get_key_material(settings)
    assert first == second
    assert counter.read_text() == "1", "команду спросили дважды — кэш не работает"

    # Срок кэша истёк: связку спрашивают заново и видят новый ключ (ротация).
    reset_cache()
    third = get_key_material(settings)
    assert third != first
    assert counter.read_text() == "2"


def test_failure_is_not_cached(tmp_path) -> None:
    """Неудачу кэшировать нельзя: вернувшееся хранилище должно сразу работать."""

    flag = tmp_path / "fail"
    flag.write_text("1")
    body = (
        "import json, pathlib, sys\n"
        f"p = pathlib.Path({str(flag)!r})\n"
        "if p.exists():\n"
        "    sys.stderr.write('sealed')\n"
        "    sys.exit(1)\n"
        f"print(json.dumps({{'keys': 'k1:{_KEY_A}'}}))\n"
    )
    command = _script(tmp_path, body)
    settings = _env_settings(
        secret_key_provider="command",
        secret_key_command=command,
        secret_key_provider_ttl_seconds=60.0,
    )

    with pytest.raises(KeyProviderError):
        get_key_material(settings)

    flag.unlink()
    assert get_key_material(settings).keys == f"k1:{_KEY_A}"


def test_command_command_is_redacted_in_settings_dump() -> None:
    """Команда может нести токен доступа к хранилищу — в выгрузке настроек её нет."""

    from app.core.config import Settings

    os.environ["APP_SECRET_KEY_COMMAND"] = "vault read -field=keys secret/app token=t0ps3cret"
    try:
        dumped = Settings().redacted()
    finally:
        os.environ.pop("APP_SECRET_KEY_COMMAND", None)
    assert "t0ps3cret" not in json.dumps(dumped, default=str)
