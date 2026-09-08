"""SEC-68 (разд. 68.1) — привязка magic link к получателю через одноразовый код.

ЗАЧЕМ. В модели угроз внешнего периметра одна строка держалась красной:
**пересланная третьему лицу ссылка**. Одноразовость помогает лишь отчасти — кто
первым откроет, тот и войдёт, и владелец ссылки об этом не узнает. Привязка
закрывает именно это: ссылка остаётся входным билетом, но обменять её на сеанс
можно только кодом, пришедшим НА УКАЗАННЫЙ АДРЕС.

Закрепляется: без кода не войти; неверный код считается попыткой перебора;
после исчерпания попыток код гасится целиком; запрос кода не тратит
использований ссылки; ответ на запрос кода одинаков для привязанной и
непривязанной ссылки; ссылка без привязки работает как прежде.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import client_portal as routes
from app.core import external_perimeter as ep
from app.models.packages import ClientPortalToken


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _request(ip: str = "203.0.113.20") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.fixture(autouse=True)
def _fresh_guard():
    ep.reset_guard()
    yield
    ep.reset_guard()


@pytest.fixture()
def sent_letters(monkeypatch):
    """Почта заменена перехватчиком: проверяем письмо, а не SMTP."""

    letters: list[dict] = []

    async def _fake_send(*, tenant_id, recipient, code, ttl_minutes):
        letters.append(
            {"tenant_id": tenant_id, "recipient": recipient, "code": code, "ttl": ttl_minutes}
        )
        return SimpleNamespace(delivered=True, reason="Код отправлен")

    monkeypatch.setattr(routes, "send_otp_code", _fake_send)
    monkeypatch.setattr(routes, "mail_channel_ready", lambda: True)
    return letters


async def _seed_link(session, *, plain: str, otp_email: str | None = None, max_uses=None):
    row = ClientPortalToken(
        tenant_id="tenant-1",
        token_hash=routes._hash_token(plain),
        package_run_id=str(uuid.uuid4()),
        scope_json={},
        expires_at=_now() + timedelta(hours=24),
        max_uses=max_uses,
        otp_email=otp_email,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_привязанная_ссылка_без_кода_не_пускает(sessionmaker, sent_letters):
    """Главное свойство: одной ссылки мало, даже если она подлинная."""

    async with sessionmaker() as session:
        await _seed_link(session, plain="otp-link-1", otp_email="client@example.com")

        with pytest.raises(HTTPException) as exc:
            await routes.create_portal_session(
                request=_request(), session=session, x_portal_token="otp-link-1", token=None
            )

        assert exc.value.status_code == 401
        assert "код" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_код_уходит_на_адрес_получателя_и_пускает(sessionmaker, sent_letters):
    async with sessionmaker() as session:
        row = await _seed_link(session, plain="otp-link-2", otp_email="client@example.com")

        answer = await routes.request_portal_otp(
            request=_request(), session=session, x_portal_token="otp-link-2", token=None
        )
        assert answer.expires_in_minutes >= 1
        assert len(sent_letters) == 1
        assert sent_letters[0]["recipient"] == "client@example.com"
        code = sent_letters[0]["code"]
        assert len(code) == 6 and code.isdigit()
        # Запрос кода НЕ тратит использований: иначе одноразовая ссылка
        # сгорала бы на попытке войти.
        assert row.uses_count == 0

        out = await routes.create_portal_session(
            request=_request(),
            session=session,
            x_portal_token="otp-link-2",
            token=None,
            code=code,
        )
        assert out.session_token
        # Код одноразовый: вошли — погасили.
        assert row.otp_code_hash is None


@pytest.mark.asyncio
async def test_код_нельзя_использовать_второй_раз(sessionmaker, sent_letters):
    async with sessionmaker() as session:
        await _seed_link(session, plain="otp-link-3", otp_email="client@example.com")
        await routes.request_portal_otp(
            request=_request(), session=session, x_portal_token="otp-link-3", token=None
        )
        code = sent_letters[0]["code"]
        await routes.create_portal_session(
            request=_request(),
            session=session,
            x_portal_token="otp-link-3",
            token=None,
            code=code,
        )

        with pytest.raises(HTTPException) as exc:
            await routes.create_portal_session(
                request=_request(),
                session=session,
                x_portal_token="otp-link-3",
                token=None,
                code=code,
            )
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_перебор_кода_гасит_код_целиком(sessionmaker, sent_letters, monkeypatch):
    """Шестизначный код без счётчика попыток перебирается за минуты."""

    async with sessionmaker() as session:
        row = await _seed_link(session, plain="otp-link-4", otp_email="client@example.com")
        await routes.request_portal_otp(
            request=_request(), session=session, x_portal_token="otp-link-4", token=None
        )
        верный = sent_letters[0]["code"]
        неверный = "000000" if верный != "000000" else "111111"

        limit = routes.get_settings().portal_otp_max_attempts
        for _ in range(limit):
            with pytest.raises(HTTPException):
                await routes.create_portal_session(
                    request=_request(),
                    session=session,
                    x_portal_token="otp-link-4",
                    token=None,
                    code=неверный,
                )

        # Попытки исчерпаны — код погашен, и ВЕРНЫЙ код больше не пускает:
        # иначе счётчик обходился бы повторными попытками.
        with pytest.raises(HTTPException) as exc:
            await routes.create_portal_session(
                request=_request(),
                session=session,
                x_portal_token="otp-link-4",
                token=None,
                code=верный,
            )
        assert exc.value.status_code == 401
        assert row.otp_code_hash is None


@pytest.mark.asyncio
async def test_истёкший_код_не_пускает(sessionmaker, sent_letters):
    async with sessionmaker() as session:
        row = await _seed_link(session, plain="otp-link-5", otp_email="client@example.com")
        await routes.request_portal_otp(
            request=_request(), session=session, x_portal_token="otp-link-5", token=None
        )
        code = sent_letters[0]["code"]
        row.otp_expires_at = _now() - timedelta(minutes=1)
        await session.flush()

        with pytest.raises(HTTPException) as exc:
            await routes.create_portal_session(
                request=_request(),
                session=session,
                x_portal_token="otp-link-5",
                token=None,
                code=code,
            )
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_ответ_не_выдаёт_есть_ли_привязка(sessionmaker, sent_letters):
    """Разный ответ позволял бы перебирать, какие ссылки к кому привязаны."""

    async with sessionmaker() as session:
        await _seed_link(session, plain="otp-link-6", otp_email="client@example.com")
        await _seed_link(session, plain="plain-link-6")

        привязанная = await routes.request_portal_otp(
            request=_request(), session=session, x_portal_token="otp-link-6", token=None
        )
        обычная = await routes.request_portal_otp(
            request=_request(), session=session, x_portal_token="plain-link-6", token=None
        )

        assert привязанная.message == обычная.message
        # Письмо ушло только по привязанной ссылке.
        assert len(sent_letters) == 1


@pytest.mark.asyncio
async def test_ссылка_без_привязки_работает_как_прежде(sessionmaker, sent_letters):
    """Разосланные ссылки не ломаются: привязка — опция, а не новое условие."""

    async with sessionmaker() as session:
        await _seed_link(session, plain="plain-link-7")

        out = await routes.create_portal_session(
            request=_request(), session=session, x_portal_token="plain-link-7", token=None
        )
        assert out.session_token
        assert sent_letters == []
