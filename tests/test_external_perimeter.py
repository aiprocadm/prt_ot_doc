"""SEC-68: anti-abuse внешнего контура и одноразовые magic links (разд. 68.1–68.2).

Что закрепляется:

* перебор токена ограничен ОТДЕЛЬНЫМ счётчиком неудач — успешные запросы его не
  тратят, поэтому низкий порог ловит атаку, не мешая легитимному клиенту;
* лимит срабатывает ДО обращения к базе: иначе каждая попытка перебора стоила бы
  нам запроса в БД;
* протухшая ссылка не считается попыткой перебора — это обычная ситуация у клиента
  со старым письмом;
* ``max_uses`` делает ссылку одноразовой, и пересланная копия исчерпывает тот же
  лимит, что и оригинал;
* TTL ссылки ограничен потолком — «вечную» ссылку нельзя выдать даже опечаткой
  в конфиге.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import external_perimeter as ep


def _request(ip: str = "203.0.113.7") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "rate_limit_enabled": True,
        "rate_limit_storage_uri": "memory://",
        "portal_rate_limit_per_ip": "1000/minute",
        "portal_auth_failures_per_ip": "3/hour",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _fresh_guard():
    ep.reset_guard()
    yield
    ep.reset_guard()


def test_failure_counter_locks_out_after_threshold() -> None:
    settings = _settings()
    request = _request()

    for _ in range(3):
        ep.assert_not_locked_out(request, settings=settings)
        ep.record_auth_failure(request, settings=settings)

    with pytest.raises(HTTPException) as excinfo:
        ep.assert_not_locked_out(request, settings=settings)
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail["code"] == "PORTAL_TOKEN_LOCKED_OUT"


def test_lockout_is_per_ip() -> None:
    """Блокировка одного адреса не должна задевать других клиентов портала."""

    settings = _settings()
    attacker, client = _request("198.51.100.1"), _request("203.0.113.9")

    for _ in range(4):
        ep.record_auth_failure(attacker, settings=settings)

    with pytest.raises(HTTPException):
        ep.assert_not_locked_out(attacker, settings=settings)
    ep.assert_not_locked_out(client, settings=settings)  # не должно бросать


def test_successful_requests_do_not_consume_the_failure_budget() -> None:
    """Иначе активный легитимный клиент сам себя заблокировал бы."""

    settings = _settings()
    request = _request("203.0.113.11")

    for _ in range(50):
        ep.enforce_portal_traffic(request, settings=settings)

    ep.assert_not_locked_out(request, settings=settings)


def test_traffic_limit_applies_per_ip() -> None:
    settings = _settings(portal_rate_limit_per_ip="2/minute")
    request = _request("198.51.100.20")

    ep.enforce_portal_traffic(request, settings=settings)
    ep.enforce_portal_traffic(request, settings=settings)
    with pytest.raises(HTTPException) as excinfo:
        ep.enforce_portal_traffic(request, settings=settings)
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail["code"] == "PORTAL_RATE_LIMITED"

    # Другой адрес не затронут.
    ep.enforce_portal_traffic(_request("198.51.100.21"), settings=settings)


def test_disabled_rate_limiting_is_a_no_op() -> None:
    settings = _settings(rate_limit_enabled=False, portal_rate_limit_per_ip="1/minute")
    request = _request("198.51.100.30")

    for _ in range(5):
        ep.enforce_portal_traffic(request, settings=settings)
        ep.record_auth_failure(request, settings=settings)
    ep.assert_not_locked_out(request, settings=settings)


def test_missing_client_is_bucketed_not_crashing() -> None:
    """ASGI-запрос без client (внутренний вызов) не должен ронять защиту."""

    settings = _settings(portal_rate_limit_per_ip="1/minute")
    faceless = SimpleNamespace(client=None)

    ep.enforce_portal_traffic(faceless, settings=settings)
    with pytest.raises(HTTPException):
        ep.enforce_portal_traffic(faceless, settings=settings)


# --- Портальные ручки целиком -------------------------------------------------------

API_PREFIX = "/api/v1"


@pytest.mark.anyio
class TestPortalTokenUsageLimit:
    async def test_single_use_link_is_rejected_on_second_use(
        self, async_client, sessionmaker, data_factory
    ) -> None:
        """Пересланная третьему лицу ссылка исчерпывает тот же лимит, что и оригинал."""

        from app.api.routes.client_portal import _hash_token
        from app.models.packages import (
            ClientPackagePreset,
            ClientPackageRun,
            ClientPortalToken,
            PackageRunStatus,
        )

        token_plain = "single-use-token-value"
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="portal-once", session=session)
            preset = ClientPackagePreset(
                code="ONE_SHOT",
                name="One shot",
                steps_json={},
                required_inputs_json=[],
                tenant_id=tenant.id,
            )
            session.add(preset)
            await session.flush()
            run = ClientPackageRun(
                preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id
            )
            session.add(run)
            await session.flush()
            session.add(
                ClientPortalToken(
                    tenant_id=tenant.id,
                    token_hash=_hash_token(token_plain),
                    package_run_id=run.id,
                    scope_json={"package_run_ids": [run.id], "download": True},
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                    max_uses=1,
                    uses_count=0,
                )
            )
            await session.commit()

        headers = {"X-Portal-Token": token_plain}
        first = await async_client.get(f"{API_PREFIX}/portal/packages", headers=headers)
        assert first.status_code == 200, first.text

        second = await async_client.get(f"{API_PREFIX}/portal/packages", headers=headers)
        assert second.status_code == 401, second.text
        assert "usage limit" in second.text

    async def test_unlimited_link_keeps_working(
        self, async_client, sessionmaker, data_factory
    ) -> None:
        """max_uses=NULL — поведение уже выданных ссылок; бэкфилл не нужен."""

        from app.api.routes.client_portal import _hash_token
        from app.models.packages import (
            ClientPackagePreset,
            ClientPackageRun,
            ClientPortalToken,
            PackageRunStatus,
        )

        token_plain = "unlimited-token-value"
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="portal-many", session=session)
            preset = ClientPackagePreset(
                code="MANY_SHOT",
                name="Many",
                steps_json={},
                required_inputs_json=[],
                tenant_id=tenant.id,
            )
            session.add(preset)
            await session.flush()
            run = ClientPackageRun(
                preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id
            )
            session.add(run)
            await session.flush()
            session.add(
                ClientPortalToken(
                    tenant_id=tenant.id,
                    token_hash=_hash_token(token_plain),
                    package_run_id=run.id,
                    scope_json={"package_run_ids": [run.id], "download": True},
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                )
            )
            await session.commit()

        headers = {"X-Portal-Token": token_plain}
        for _ in range(3):
            response = await async_client.get(f"{API_PREFIX}/portal/packages", headers=headers)
            assert response.status_code == 200, response.text
