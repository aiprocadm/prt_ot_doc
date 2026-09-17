"""SEC-68 — обмен ссылочного токена портала на короткоживущий сеансовый.

Закрепляется:

* обмен проходит все anti-abuse проверки и тратит ОДНО использование ссылки;
* сеансовые запросы использований НЕ тратят — одноразовая ссылка (max_uses=1)
  становится пригодной для UI из многих запросов;
* отзыв ссылки убивает и сеанс (сеанс перепроверяет ссылку в базе);
* срок сеанса не выходит за срок ссылки;
* подделанный сеансовый токен — 401 и попытка перебора (счётчик неудач).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import client_portal as routes
from app.core import external_perimeter as ep
from app.core.security import verify_token
from app.models.packages import ClientPortalToken


# НЕ модульная константа: сбор тестов происходит в начале прогона, а сам тест
# может стартовать спустя >30 минут — ссылка «на полчаса» от времени импорта
# к этому моменту уже истекла бы (флейк долгих прогонов).
def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _request(ip: str = "203.0.113.10") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.fixture(autouse=True)
def _fresh_guard():
    ep.reset_guard()
    yield
    ep.reset_guard()


async def _seed_link(session, *, plain: str, max_uses=None, expires_in_h=24, revoked=False):
    row = ClientPortalToken(
        tenant_id="tenant-1",
        token_hash=routes._hash_token(plain),
        package_run_id=str(uuid.uuid4()),
        scope_json={},
        expires_at=_now() + timedelta(hours=expires_in_h),
        revoked_at=_now() if revoked else None,
        max_uses=max_uses,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_exchange_returns_session_and_burns_one_use(sessionmaker):
    async with sessionmaker() as session:
        row = await _seed_link(session, plain="link-token-1", max_uses=1)
        out = await routes.create_portal_session(
            request=_request(),
            session=session,
            x_portal_token="link-token-1",
        )
        assert row.uses_count == 1
        claims = verify_token(out.session_token, expected_type="portal_session")
        assert claims["sub"] == str(row.id)
        # повторный обмен по одноразовой ссылке невозможен
        with pytest.raises(HTTPException) as exc:
            await routes.create_portal_session(
                request=_request(),
                session=session,
                x_portal_token="link-token-1",
            )
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_session_requests_do_not_burn_uses(sessionmaker):
    async with sessionmaker() as session:
        row = await _seed_link(session, plain="link-token-2", max_uses=1)
        out = await routes.create_portal_session(
            request=_request(), session=session, x_portal_token="link-token-2"
        )
        assert row.uses_count == 1
        for _ in range(3):
            auth = await routes._portal_auth(
                request=_request(),
                session=session,
                x_portal_session=out.session_token,
                x_portal_token=None,
            )
            assert auth.tenant_id == "tenant-1"
        assert row.uses_count == 1  # сеанс не тратит использования


@pytest.mark.asyncio
async def test_revoking_link_kills_session(sessionmaker):
    async with sessionmaker() as session:
        row = await _seed_link(session, plain="link-token-3")
        out = await routes.create_portal_session(
            request=_request(), session=session, x_portal_token="link-token-3"
        )
        row.revoked_at = _now()
        await session.flush()
        with pytest.raises(HTTPException) as exc:
            await routes._portal_auth(
                request=_request(),
                session=session,
                x_portal_session=out.session_token,
                x_portal_token=None,
            )
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_session_expiry_capped_by_link_expiry(sessionmaker):
    """Ссылка умирает через полчаса → сеанс не может жить дольше неё."""
    async with sessionmaker() as session:
        await _seed_link(session, plain="link-token-4", expires_in_h=0.5)
        out = await routes.create_portal_session(
            request=_request(), session=session, x_portal_token="link-token-4"
        )
        claims = verify_token(out.session_token, expected_type="portal_session")
        exp = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
        assert exp <= _now() + timedelta(minutes=31)


@pytest.mark.asyncio
async def test_forged_session_is_401_and_counts_as_failure(sessionmaker):
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes._portal_auth(
                request=_request("198.51.100.77"),
                session=session,
                x_portal_session="forged.jwt.token",
                x_portal_token=None,
            )
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_token_in_address_is_no_longer_accepted(sessionmaker):
    """Срез-213: ключ от чужих документов не ходит в адресе страницы.

    Раньше этот тест закреплял ОБРАТНОЕ («старый ?token= ещё работает») и после
    среза-213 падал на main — контракт сменили, тест нет. Теперь закрепляется
    решение: у проверки портала нет параметра из адреса вовсе, а ссылка
    предъявляется заголовком.
    """

    import inspect

    assert "token" not in inspect.signature(routes._portal_auth).parameters
    async with sessionmaker() as session:
        row = await _seed_link(session, plain="link-token-5")
        auth = await routes._portal_auth(
            request=_request(),
            session=session,
            x_portal_session=None,
            x_portal_token="link-token-5",
        )
        assert auth.tenant_id == "tenant-1"
        assert row.uses_count == 1
