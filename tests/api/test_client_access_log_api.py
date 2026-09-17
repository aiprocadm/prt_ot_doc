"""SEC-63 (Доп. №3 разд. 63.2): журнал доступа в кабинете САМОГО клиента.

Срез-2 SEC-63 дал такой журнал в кабинете АУТСОРСЕРА, с пометкой «показать его
клиенту — обязанность аутсорсера по договору». Здесь закрепляется, что клиент в
режиме Dedicated видит его у себя — и видит ТОЛЬКО про себя.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.models import AuditLog, RoleEnum, Tenant

MY_LOG = "/api/v1/my-access-log"
_WHEN = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _tenants() -> dict[str, str]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = {
            record.slug: record.id
            for record in (
                (await session.execute(select(Tenant).where(Tenant.slug.in_(["beta", "acme"]))))
                .scalars()
                .all()
            )
        }
        return rows


async def _serve(outsourcer_id: str, *, client_slug: str, name: str = "ООО Ромашка") -> str:
    """Завести подопечного у аутсорсера и связать с арендатором клиента."""

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        row = ManagedClient(
            tenant_id=outsourcer_id,
            name=name,
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug=client_slug,
            contract_status=ContractStatus.ACTIVE,
        )
        session.add(row)
        await session.commit()
        return row.id


async def _log_entry(outsourcer_id: str, mcid: str, *, email: str = "spec@beta.ru") -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        session.add(
            AuditLog(
                tenant_id=outsourcer_id,
                when=_WHEN,
                actor_type="user",
                actor_email=email,
                action="managed_client.context.enter",
                object_type="managed_client",
                object_id=mcid,
                ip="10.0.0.7",
                correlation_id="trace-1",
                details={"meta_json": {"method": "GET", "action": "/api/v1/persons"}},
            )
        )
        await session.commit()


async def _client_headers(make_auth_headers, role=RoleEnum.ADMIN, email="admin@acme.ru"):
    return await make_auth_headers(role, tenant="acme", email=email)


@pytest.mark.anyio
async def test_клиент_видит_кто_работал_в_его_данных(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _tenants()
    mcid = await _serve(ids["beta"], client_slug="acme")
    await _log_entry(ids["beta"], mcid)

    response = await async_client.get(MY_LOG, headers=await _client_headers(make_auth_headers))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["actor_email"] == "spec@beta.ru"
    # Имя обслуживающей компании: «кто именно» — половина ответа на вопрос.
    assert body["served_by"]


@pytest.mark.anyio
async def test_чужие_обращения_клиенту_не_видны(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """У аутсорсера много подопечных; чужие обращения — не дело клиента."""

    ids = await _tenants()
    mine = await _serve(ids["beta"], client_slug="acme")
    other = await _serve(ids["beta"], client_slug="someone-else", name="ООО Чужой")
    await _log_entry(ids["beta"], mine, email="spec@beta.ru")
    await _log_entry(ids["beta"], other, email="other@beta.ru")

    body = (await async_client.get(MY_LOG, headers=await _client_headers(make_auth_headers))).json()

    assert body["total"] == 1
    assert body["items"][0]["actor_email"] == "spec@beta.ru"


@pytest.mark.anyio
async def test_необслуживаемый_арендатор_получает_объяснение(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Пустой список без слов читается как поломка, а не как «никто не заходил»."""

    await _tenants()

    response = await async_client.get(MY_LOG, headers=await _client_headers(make_auth_headers))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["served_by"] is None
    assert "не работает обслуживающая компания" in body["summary"]


@pytest.mark.anyio
async def test_рядовому_сотруднику_журнал_закрыт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """В журнале видно, кто из подрядчиков заходил, — это дело ответственного."""

    ids = await _tenants()
    mcid = await _serve(ids["beta"], client_slug="acme")
    await _log_entry(ids["beta"], mcid)

    response = await async_client.get(
        MY_LOG,
        headers=await _client_headers(
            make_auth_headers, role=RoleEnum.EMPLOYEE, email="worker@acme.ru"
        ),
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_модуль_аутсорсера_не_требуется(async_client: AsyncClient, make_auth_headers) -> None:
    """У клиента модуля `managed_clients` нет и быть не должно.

    Право знать, кто трогал твои данные, не может зависеть от чужой подписки.
    """

    ids = await _tenants()
    mcid = await _serve(ids["beta"], client_slug="acme")
    await _log_entry(ids["beta"], mcid)

    response = await async_client.get(MY_LOG, headers=await _client_headers(make_auth_headers))

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


@pytest.mark.anyio
async def test_записи_не_дублируются_в_арендатора_клиента(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Зеркалирование сломало бы цепочку несмываемости у клиента.

    Аудит подписан и проверяется на целостность (SEC-63 срез-2); вставка в него
    чужих строк сделала бы проверку у клиента ложно-отрицательной.
    """

    ids = await _tenants()
    mcid = await _serve(ids["beta"], client_slug="acme")
    await _log_entry(ids["beta"], mcid)

    await async_client.get(MY_LOG, headers=await _client_headers(make_auth_headers))

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        mirrored = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == ids["acme"],
                    AuditLog.action == "managed_client.context.enter",
                )
            )
        ).all()

    assert mirrored == []


@pytest.mark.anyio
async def test_период_сужает_выборку(async_client: AsyncClient, make_auth_headers) -> None:
    ids = await _tenants()
    mcid = await _serve(ids["beta"], client_slug="acme")
    await _log_entry(ids["beta"], mcid)

    body = (
        await async_client.get(
            MY_LOG,
            params={"since": "2026-09-01T00:00:00Z"},
            headers=await _client_headers(make_auth_headers),
        )
    ).json()

    assert body["total"] == 0
    # Обслуживающая компания названа и когда записей за период нет.
    assert body["served_by"]
