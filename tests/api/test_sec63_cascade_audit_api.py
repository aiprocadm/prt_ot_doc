"""SEC-63.1: каскад виден и доказуем (Доп. №3 разд. 63.1, четвёртая угроза).

ТЗ: «каскадное отключение как оружие … safe read-only вместо удаления; АУДИТ
КАСКАДА; защита managing tenant». Режим чтения сделан BIZ-52 срезом-3, защита
управляющего была и раньше — здесь появляется след и предупреждение.

Плюс обязательный по ТЗ **cross-reseller deny**: партнёр не должен ни увидеть
последствия чужой приостановки, ни выполнить её.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import AuditLog, RoleEnum, Tenant

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _shape_tree() -> dict[str, str]:
    """`beta` — партнёр с клиентами `acme` и `gamma`; `delta` — партнёр-сосед."""

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
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
        rows["gamma"].parent_id = rows["beta"].id
        rows["zeta"].parent_id = None
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _platform(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-cascade@example.com"
    )


async def _partner(make_auth_headers, slug: str = "delta") -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant=slug, email=f"admin-{slug}-cascade@example.com"
    )


async def _cascade_audit_rows() -> list[AuditLog]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        return list(
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "tenant.suspension_cascade")
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.anyio
async def test_предупреждение_до_нажатия(async_client: AsyncClient, make_auth_headers) -> None:
    """Оператор должен видеть последствие ДО приостановки, а не по жалобам."""

    ids = await _shape_tree()

    response = await async_client.get(
        f"{BASE}/{ids['beta']}/cascade", headers=await _platform(make_auth_headers)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_reseller"] is True
    assert sorted(body["cascade_affected"]) == ["acme", "gamma"]
    assert "2" in body["cascade_summary"]


@pytest.mark.anyio
async def test_предпросмотр_ничего_не_меняет(async_client: AsyncClient, make_auth_headers) -> None:
    ids = await _shape_tree()

    await async_client.get(
        f"{BASE}/{ids['beta']}/cascade", headers=await _platform(make_auth_headers)
    )

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        partner = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()
        assert partner.is_active is True
    assert await _cascade_audit_rows() == []


@pytest.mark.anyio
async def test_приостановка_возвращает_кого_задело(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['beta']}/status",
        headers=await _platform(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_active"] is False
    assert sorted(body["cascade_affected"]) == ["acme", "gamma"]


@pytest.mark.anyio
async def test_каскад_попадает_в_аудит(async_client: AsyncClient, make_auth_headers) -> None:
    """Без следа нельзя доказать, кого задело и что данные не тронуты."""

    ids = await _shape_tree()

    await async_client.patch(
        f"{BASE}/{ids['beta']}/status",
        headers=await _platform(make_auth_headers),
        json={"is_active": False},
    )

    rows = await _cascade_audit_rows()
    assert len(rows) == 1
    details = rows[0].details or {}
    assert details.get("affected_count") == 2
    assert sorted(details.get("affected_slugs") or []) == ["acme", "gamma"]
    assert details.get("activating") is False


@pytest.mark.anyio
async def test_возобновление_тоже_оставляет_след(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Обе стороны каскада обязаны быть одинаково прослеживаемы."""

    ids = await _shape_tree()
    headers = await _platform(make_auth_headers)

    await async_client.patch(
        f"{BASE}/{ids['beta']}/status", headers=headers, json={"is_active": False}
    )
    await async_client.patch(
        f"{BASE}/{ids['beta']}/status", headers=headers, json={"is_active": True}
    )

    rows = await _cascade_audit_rows()
    assert len(rows) == 2
    assert {bool((row.details or {}).get("activating")) for row in rows} == {False, True}


@pytest.mark.anyio
async def test_у_обычного_клиента_каскада_нет(async_client: AsyncClient, make_auth_headers) -> None:
    """Приостановка клиента не пишет каскадную запись: каскада у него нет."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['zeta']}/status",
        headers=await _platform(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["cascade_affected"] == []
    assert await _cascade_audit_rows() == []


@pytest.mark.anyio
async def test_партнёр_без_клиентов_даёт_запись_с_нулём(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Партнёр приостановлен, клиентов нет» — такой же факт, как «задето двое»."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['delta']}/status",
        headers=await _platform(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["cascade_affected"] == []
    rows = await _cascade_audit_rows()
    assert len(rows) == 1
    assert (rows[0].details or {}).get("affected_count") == 0


class TestCrossResellerDeny:
    """Обязательный по ТЗ тест: партнёр не дотягивается до чужого контура."""

    @pytest.mark.anyio
    async def test_партнёр_не_видит_каскад_соседа(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        ids = await _shape_tree()

        response = await async_client.get(
            f"{BASE}/{ids['beta']}/cascade",
            headers=await _partner(make_auth_headers, "delta"),
        )

        # 404, а не 403: даже факт существования соседа не подтверждаем.
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_партнёр_не_приостановит_соседа(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        ids = await _shape_tree()

        response = await async_client.patch(
            f"{BASE}/{ids['beta']}/status",
            headers=await _partner(make_auth_headers, "delta"),
            json={"is_active": False},
        )

        assert response.status_code == 404
        assert await _cascade_audit_rows() == []

    @pytest.mark.anyio
    async def test_партнёр_не_видит_каскад_чужого_клиента(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """Клиент соседа — тоже чужой контур, хотя он и не партнёр."""

        ids = await _shape_tree()

        response = await async_client.get(
            f"{BASE}/{ids['acme']}/cascade",
            headers=await _partner(make_auth_headers, "delta"),
        )

        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_клиенту_предпросмотр_каскада_закрыт(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        ids = await _shape_tree()
        headers = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme-cascade@example.com"
        )

        response = await async_client.get(f"{BASE}/{ids['beta']}/cascade", headers=headers)

        assert response.status_code == 403
        assert response.json()["code"] == "FLEET_ACCESS_FORBIDDEN"
