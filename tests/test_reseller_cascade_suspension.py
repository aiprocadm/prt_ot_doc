"""BIZ-52 срез-3 (разд. 52.1): приостановка партнёра — «только чтение» у клиентов.

ТЗ: «Каскадное отключение: приостановка reseller'а безопасно приостанавливает
его клиентов (safe read-only), но не удаляет данные».

Что закрепляется:

* клиент приостановленного партнёра ЧИТАЕТ, но не пишет;
* отказ называет виновника — иначе клиент идёт в поддержку платформы и слышит
  «у нас всё работает»;
* **вход и выгрузка остаются доступны** — иначе простой партнёра превратился бы
  в захват данных его клиентов;
* возобновление партнёра снимает режим СРАЗУ, без записи в базу и без кэша;
* прямой клиент платформы и клиент другого, работающего партнёра не задеты;
* **данные не удаляются** — режим ничего не пишет.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.domains.reseller import RESELLER_KIND
from app.middleware.reseller_suspension import RESELLER_SUSPENDED_READ_ONLY
from app.models.models import Company, RoleEnum, Tenant

API_PREFIX = "/api/v1"


async def _shape_tree(sessionmaker) -> dict[str, str]:
    """`beta` — партнёр с клиентом `acme`; `delta` — партнёр с клиентом `gamma`."""

    async with sessionmaker() as session:
        rows = {
            record.slug: record
            for record in (
                (
                    await session.execute(
                        select(Tenant).where(
                            Tenant.slug.in_(["beta", "delta", "acme", "gamma", "zeta"])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["delta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        rows["gamma"].parent_id = rows["delta"].id
        rows["zeta"].parent_id = None
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _set_active(sessionmaker, slug: str, active: bool) -> None:
    async with sessionmaker() as session:
        record = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
        record.is_active = active
        await session.commit()


@pytest.mark.anyio
class TestКаскаднаяПриостановка:
    async def test_клиент_приостановленного_партнёра_не_пишет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        await _shape_tree(sessionmaker)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme-cascade@example.com"
        )
        await _set_active(sessionmaker, "beta", False)

        response = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Новая компания"}, headers=headers
        )

        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == RESELLER_SUSPENDED_READ_ONLY
        # Виновник назван: иначе клиент идёт в поддержку платформы впустую.
        assert detail["reseller_name"]

    async def test_чтение_продолжает_работать(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Только чтение» означает, что читать МОЖНО — иначе это блокировка."""

        await _shape_tree(sessionmaker)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme-cascade@example.com"
        )
        await _set_active(sessionmaker, "beta", False)

        response = await async_client.get(f"{API_PREFIX}/companies", headers=headers)

        assert response.status_code == 200, response.text

    async def test_выгрузка_данных_остаётся_доступна(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Иначе простой партнёра стал бы захватом данных его клиента."""

        await _shape_tree(sessionmaker)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme-cascade@example.com"
        )
        await _set_active(sessionmaker, "beta", False)

        response = await async_client.post(
            f"{API_PREFIX}/offboarding/request",
            json={"reason": "партнёр не работает", "grace_days": 30},
            headers=headers,
        )

        assert response.status_code != 409, response.text

    async def test_возобновление_партнёра_снимает_режим_сразу(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Кэша нет: клиент не должен ждать, когда партнёр уже вернулся."""

        await _shape_tree(sessionmaker)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme-cascade@example.com"
        )
        await _set_active(sessionmaker, "beta", False)
        blocked = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Раз"}, headers=headers
        )
        assert blocked.status_code == 409

        await _set_active(sessionmaker, "beta", True)
        allowed = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Два"}, headers=headers
        )

        assert allowed.status_code == 201, allowed.text

    async def test_данные_клиента_не_удаляются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Прямое требование ТЗ: «но не удаляет данные»."""

        ids = await _shape_tree(sessionmaker)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme-cascade@example.com"
        )
        created = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "До приостановки"}, headers=headers
        )
        assert created.status_code == 201, created.text

        await _set_active(sessionmaker, "beta", False)

        async with sessionmaker() as session:
            survived = (
                (await session.execute(select(Company).where(Company.tenant_id == ids["acme"])))
                .scalars()
                .all()
            )
        assert survived, "строки клиента обязаны пережить приостановку партнёра"


@pytest.mark.anyio
class TestКогоКаскадНеКасается:
    async def test_клиент_работающего_партнёра_пишет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        await _shape_tree(sessionmaker)
        await _set_active(sessionmaker, "beta", False)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="gamma", email="admin-gamma-cascade@example.com"
        )

        response = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Сосед"}, headers=headers
        )

        assert response.status_code == 201, response.text

    async def test_прямой_клиент_платформы_не_задет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """У него нет родителя — и он не должен стоить ни одного запроса к базе."""

        await _shape_tree(sessionmaker)
        await _set_active(sessionmaker, "beta", False)
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="zeta", email="admin-zeta-cascade@example.com"
        )

        response = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Свой"}, headers=headers
        )

        assert response.status_code == 201, response.text
