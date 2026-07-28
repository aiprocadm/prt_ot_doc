"""SEC-67: скрипт ротации ключа шифрования секретов (разд. 67.2).

Юнит-тесты шифра закрепляют формат и поведение связки ключей; здесь проверяется
второй шаг ротации целиком: пройти по хранимым секретам и перевести их на активный
ключ, не потеряв плейнтекст и не переписывая уже переведённые строки.
"""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core import secret_cipher
from app.models.models import WebhookEndpoint
from tests.utils.factories import TestDataFactory

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_OLD = base64.b64encode(b"O" * 32).decode()
KEY_NEW = base64.b64encode(b"N" * 32).decode()


def _load_script():
    """``scripts/`` не пакет — грузим по пути."""

    path = REPO_ROOT / "scripts" / "rotate_secret_keys.py"
    spec = importlib.util.spec_from_file_location("rotate_secret_keys", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(keys: str, active: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        secret_encryption_key="",
        secret_encryption_keys=keys,
        secret_encryption_active_kid=active,
        app_env="test",
        secret_key="unit-secret",
    )


@pytest.fixture()
def keyring_env(monkeypatch: pytest.MonkeyPatch):
    """Подменяет связку ключей, которую видит модуль шифра (и, значит, скрипт)."""

    state = {"settings": _settings(f"old:{KEY_OLD}")}
    monkeypatch.setattr(secret_cipher, "_settings", lambda: state["settings"])
    return state


@pytest.mark.anyio
async def test_rotation_moves_stored_secrets_to_the_active_key(
    keyring_env, sessionmaker, data_factory: TestDataFactory
) -> None:
    script = _load_script()

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        endpoint = WebhookEndpoint(
            tenant_id=str(tenant.id),
            name="rotation-probe",
            url="https://example.test/hook",
            secret=secret_cipher.encrypt_secret("s3cr3t"),
            is_enabled=True,
            subscribed_events=[],
            timeout_ms=1000,
        )
        session.add(endpoint)
        await session.commit()
        endpoint_id = endpoint.id

    assert secret_cipher.key_id_of(endpoint.secret) == "old"

    # Ключ добавлен в связку и объявлен активным — шаг 1 ротации.
    keyring_env["settings"] = _settings(f"old:{KEY_OLD},new:{KEY_NEW}", active="new")

    stats, rewritten = await script._rotate(apply=True)

    assert rewritten >= 1
    assert any(label.endswith(":old") for label in stats)

    async with sessionmaker() as session:
        stored = (
            await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id))
        ).scalar_one()
    assert secret_cipher.key_id_of(stored.secret) == "new"
    # Главное: плейнтекст пережил ротацию — иначе подписи вебхуков перестанут сходиться.
    assert secret_cipher.decrypt_secret(stored.secret) == "s3cr3t"

    # Повторный прогон ничего не переписывает.
    _stats2, rewritten2 = await script._rotate(apply=True)
    assert rewritten2 == 0


@pytest.mark.anyio
async def test_check_mode_reports_without_writing(
    keyring_env, sessionmaker, data_factory: TestDataFactory
) -> None:
    script = _load_script()

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="rot-check", session=session)
        session.add(
            WebhookEndpoint(
                tenant_id=str(tenant.id),
                name="check-probe",
                url="https://example.test/hook2",
                secret=secret_cipher.encrypt_secret("keep-me"),
                is_enabled=True,
                subscribed_events=[],
                timeout_ms=1000,
            )
        )
        await session.commit()

    keyring_env["settings"] = _settings(f"old:{KEY_OLD},new:{KEY_NEW}", active="new")

    stats, rewritten = await script._rotate(apply=False)

    assert rewritten == 0, "--check не должен писать в базу"
    assert stats, "отчёт обязан показать, что секреты на отставном ключе есть"
