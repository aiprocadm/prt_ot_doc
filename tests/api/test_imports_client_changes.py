"""BIZ-51 срез-2: загрузка кадровых пополняет ленту клиента (разд. 51.2).

Срез-1 дал ленту, которую заполняют руками. ТЗ называет ручной ввод лишь
первым из четырёх источников; второй — импорт с diff «что изменилось с
прошлого раза». Здесь закрепляется связка целиком, а правила diff'а проверены
по отдельности в ``tests/test_client_change_signals.py``.

Что закрепляется:

* **первая загрузка ленту не засоряет** — привезти штатку не значит принять
  весь штат на работу в один день;
* следующая загрузка нового человека даёт «Принят», статус `terminated` —
  «Уволен»;
* запись помечена источником `import`: доверие к машинной записи и к внесённой
  человеком разное;
* компания, которую аутсорсер не обслуживает, ленты не получает;
* повторный разбор той же партии ленту не удваивает.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.client_changes import ClientChange
from app.models.imports import ImportBatch
from app.models.managed_clients import ManagedClient
from app.models.models import RoleEnum
from app.services.client_change_signals import record_client_changes_for_batch

API = "/api/v1/imports"
HEADER = "Организация,Фамилия,Имя,Табельный номер,Статус\n"
COMPANY = "АКМЕ"


def _csv(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode("utf-8")


def _upload(content: bytes, name: str = "staff.csv") -> dict:
    return {"file": (name, content, "text/csv")}


async def _trusted():
    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


@pytest.fixture()
async def served_company(sessionmaker, data_factory):
    """Компания, которую аутсорсер обслуживает как клиента."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name=COMPANY, session=session)
        session.add(
            ManagedClient(
                tenant_id=tenant.id,
                name="ООО АКМЕ",
                mode=ManagedClientMode.LIGHTWEIGHT,
                contract_status=ContractStatus.ACTIVE,
                company_id=company.id,
            )
        )
        await session.commit()
        return tenant, company


async def _apply(async_client: AsyncClient, headers, content: bytes) -> dict:
    response = await async_client.post(
        f"{API}/persons/apply", files=_upload(content), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["batch"]


async def _feed(tenant_id: str) -> list[ClientChange]:
    async with await _trusted() as session:
        rows = (
            await session.execute(
                select(ClientChange)
                .where(ClientChange.tenant_id == tenant_id)
                .order_by(ClientChange.created_at)
            )
        ).scalars()
        return list(rows)


@pytest.mark.anyio
class TestImportFeedsTheChangeLog:
    async def test_первая_загрузка_ленту_не_засоряет(
        self, async_client: AsyncClient, make_auth_headers, served_company
    ) -> None:
        """500 строк первой штатки — это перенос данных, а не 500 приёмов."""

        tenant, _ = served_company
        headers = await make_auth_headers(RoleEnum.ADMIN)

        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))

        assert await _feed(tenant.id) == []

    async def test_следующая_загрузка_даёт_приём_на_работу(
        self, async_client: AsyncClient, make_auth_headers, served_company
    ) -> None:
        tenant, _ = served_company
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))

        await _apply(async_client, headers, _csv(f"{COMPANY},Петров,Пётр,002,active\n"))

        feed = await _feed(tenant.id)
        assert [row.kind.value for row in feed] == ["employee_hired"]
        assert "Петров" in feed[0].summary

    async def test_запись_помечена_источником(
        self, async_client: AsyncClient, make_auth_headers, served_company
    ) -> None:
        # Внесённое человеком и увиденное в выгрузке проверяют по-разному.
        tenant, _ = served_company
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))

        batch = await _apply(async_client, headers, _csv(f"{COMPANY},Петров,Пётр,002,active\n"))

        feed = await _feed(tenant.id)
        assert feed[0].source == "import"
        assert feed[0].source_ref == batch["id"]

    async def test_смена_статуса_на_уволен_попадает_в_ленту(
        self, async_client: AsyncClient, make_auth_headers, served_company
    ) -> None:
        tenant, _ = served_company
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))

        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,terminated\n"))

        feed = await _feed(tenant.id)
        assert [row.kind.value for row in feed] == ["employee_left"]
        assert "Иванов" in feed[0].summary

    async def test_необслуживаемая_компания_ленты_не_получает(
        self, async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Своя организация аутсорсера — не клиент, ленты сопровождения у неё нет."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await data_factory.create_company(tenant=tenant, name=COMPANY, session=session)
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))

        await _apply(async_client, headers, _csv(f"{COMPANY},Петров,Пётр,002,active\n"))

        assert await _feed(tenant.id) == []

    async def test_повторный_разбор_партии_ленту_не_удваивает(
        self, async_client: AsyncClient, make_auth_headers, served_company, sessionmaker
    ) -> None:
        """Ретрай брокера не должен делать одну работу дважды."""

        tenant, _ = served_company
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))
        batch_id = (
            await _apply(async_client, headers, _csv(f"{COMPANY},Петров,Пётр,002,active\n"))
        )["id"]
        assert len(await _feed(tenant.id)) == 1

        async with await _trusted() as session:
            batch = (
                await session.execute(select(ImportBatch).where(ImportBatch.id == batch_id))
            ).scalar_one()
            await record_client_changes_for_batch(session, batch)
            await session.commit()

        assert len(await _feed(tenant.id)) == 1

    async def test_сбой_разбора_не_роняет_импорт(
        self, async_client: AsyncClient, make_auth_headers, served_company, monkeypatch
    ) -> None:
        """Данные уже записаны: вспомогательный разбор не превращает успех в 500."""

        tenant, _ = served_company
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _apply(async_client, headers, _csv(f"{COMPANY},Иванов,Иван,001,active\n"))

        from app.services import client_change_signals as signals_module

        def _boom(*args, **kwargs):
            raise RuntimeError("движок правил упал")

        monkeypatch.setattr(signals_module, "signals_for_batch", _boom, raising=True)

        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv(f"{COMPANY},Петров,Пётр,002,active\n")),
            headers=headers,
        )

        assert response.status_code == 201, response.text
        assert await _feed(tenant.id) == []
