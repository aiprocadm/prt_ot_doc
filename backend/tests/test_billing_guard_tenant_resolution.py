"""Биллинг-гейт обязан находить арендатора по ЛЮБОМУ виду заголовка ``X-Tenant``.

Дефект, найденный в волне OPS-72 и закрытый здесь: middleware искала арендатора
запросом `Tenant.slug == заголовок`. В `X-Tenant` приходит не только slug — у
клиентов и в тестах там бывает UUID или код. При таком заголовке арендатор
НЕ НАХОДИЛСЯ, и ветка «не нашли — пропускаем» отдавала запрос дальше: гейт
переставал считать лимиты и блокировать неоплаченные подписки, но выглядел
работающим. Это fail-open — отказ защиты, неотличимый от разрешения.

Здесь закрепляется, что резолвер общий (`_fetch_tenant_by_identifier`, тот же,
что у tenant-middleware и офбординга) и что проверка лимитов действительно
вызывается при UUID-заголовке.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.middleware import billing_guard
from app.middleware.billing_guard import BillingGuardMiddleware
from app.models.models import Tenant

TENANT_UUID = "11111111-2222-3333-4444-555555555555"


def _request(path: str = "/api/v1/persons", *, tenant_header: str | None = TENANT_UUID) -> Request:
    headers = []
    if tenant_header is not None:
        headers.append((b"x-tenant", tenant_header.encode()))
    return Request({"type": "http", "method": "POST", "path": path, "headers": headers})


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _RecordingBillingService:
    """Запоминает, на каком арендаторе и по какому действию звали проверку."""

    calls: list[tuple[str, str]] = []

    def __init__(self, session):  # noqa: D107 - совместимость с реальным конструктором
        self.session = session

    async def assert_allowed(self, tenant: Tenant, action: str) -> None:
        type(self).calls.append((tenant.slug, action))


@pytest.fixture()
def guard(monkeypatch: pytest.MonkeyPatch):
    tenant = Tenant(
        id=TENANT_UUID, slug="acme", name="ACME", code="acme-1", schema_name="tenant_acme"
    )
    pinned: list[str] = []

    async def _fetch(identifier: str) -> Tenant:
        # Общий резолвер понимает slug / код / UUID. Здесь достаточно того,
        # что middleware зовёт именно его, а не собственный запрос по slug.
        if identifier in {tenant.slug, tenant.code, tenant.id}:
            return tenant
        raise HTTPException(status_code=404, detail="Tenant not found")

    def _session_local(**kwargs):
        pinned.append(kwargs.get("tenant"))
        return _FakeSession()

    _RecordingBillingService.calls = []
    monkeypatch.setattr(billing_guard, "_fetch_tenant_by_identifier", _fetch)
    monkeypatch.setattr(billing_guard, "AsyncSessionLocal", _session_local)
    monkeypatch.setattr(billing_guard, "BillingService", _RecordingBillingService)
    return BillingGuardMiddleware(app=None), pinned


async def _call(middleware: BillingGuardMiddleware, request: Request) -> str:
    async def _next(_request):
        return "passed-through"

    return await middleware.dispatch(request, _next)


@pytest.mark.asyncio
async def test_uuid_tenant_header_still_reaches_the_billing_check(guard) -> None:
    """Главный дефект: с UUID в заголовке гейт молчал."""

    middleware, _pinned = guard

    result = await _call(middleware, _request())

    assert result == "passed-through"
    assert _RecordingBillingService.calls == [("acme", "persons.create")]


@pytest.mark.asyncio
async def test_tenant_code_header_also_reaches_the_check(guard) -> None:
    """Код арендатора — второй законный вид заголовка.

    Код берётся в нижнем регистре намеренно: `resolve_tenant_slug` приводит
    заголовок к lower() ДО поиска, поэтому арендатор с заглавными буквами в
    `code` по коду не найдётся. Это поведение общего резолвера, а не биллинга,
    и трогать его отсюда нельзя — на нём стоит вся tenant-middleware. Записано
    как отдельная находка; slug и UUID (они и так в нижнем регистре) не задеты.
    """

    middleware, _pinned = guard

    await _call(middleware, _request(tenant_header="acme-1"))

    assert _RecordingBillingService.calls == [("acme", "persons.create")]


@pytest.mark.asyncio
async def test_session_is_pinned_to_the_resolved_slug_not_the_raw_header(guard) -> None:
    """С UUID в ``tenant=`` search_path указывал бы на несуществующую схему."""

    middleware, pinned = guard

    await _call(middleware, _request())

    assert pinned == ["acme"]


@pytest.mark.asyncio
async def test_unknown_tenant_is_left_to_the_normal_handler(guard) -> None:
    middleware, _pinned = guard

    result = await _call(middleware, _request(tenant_header="no-such-tenant"))

    assert result == "passed-through"
    assert _RecordingBillingService.calls == []


@pytest.mark.asyncio
async def test_auth_and_billing_paths_stay_exempt(guard) -> None:
    middleware, _pinned = guard

    await _call(middleware, _request(path="/api/v1/auth/login"))
    await _call(middleware, _request(path="/api/v1/billing/plans"))

    assert _RecordingBillingService.calls == []
