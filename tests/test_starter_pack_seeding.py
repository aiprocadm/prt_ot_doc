"""BIZ-52 срез-7: эталонный набор становится настоящими справочниками (разд. 52.3).

До этой волны набор клался целиком в `tenant.settings["starter_pack"]`, это поле
не читал никто, а отчёт рапортовал «starter_pack created» — новый клиент получал
пустые справочники и уверенность, что они заполнены.

Тесты гоняют НАСТОЯЩИЙ шаг выдачи, а не разбор файла: разбор уже проверен
отдельно (`test_reseller_starter_pack.py`), а здесь важно, что строки доезжают
до базы.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.master_data import Position
from app.models.models import Company, Tenant
from app.models.safety_core import Hazard, RiskMeasure
from app.services.tenants.bootstrap.service import BootstrapTenantService


async def _bootstrap(session, monkeypatch, slug: str):
    """Выдать арендатора, отключив то, что к справочникам отношения не имеет."""

    async def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("app.services.tenants.bootstrap.service.seed_authz_catalog", _noop)
    monkeypatch.setattr(
        "app.services.tenants.bootstrap.service.aensure_tenant_schema", _noop
    )
    service = BootstrapTenantService(session)
    monkeypatch.setattr(service, "_ensure_tenant_settings", _noop)
    monkeypatch.setattr(service, "_ensure_plan", _noop)
    monkeypatch.setattr(service, "_ensure_owner", _noop)
    monkeypatch.setattr(service, "_log_bootstrap_event", _noop)
    summary = await service.run(
        tenant_slug=slug,
        tenant_name=f"ООО {slug}",
        owner_email=f"owner@{slug}.example.com",
        owner_password="Secret123!",
    )
    await session.flush()
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == slug))
    ).scalar_one()
    return summary, tenant


@pytest.mark.anyio
async def test_должности_эталона_становятся_строками(sessionmaker, monkeypatch) -> None:
    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "sp-positions")

        names = {
            name
            for name in (
                await session.execute(
                    select(Position.name).where(Position.tenant_id == tenant.id)
                )
            ).scalars()
        }

    assert "Специалист ОТ" in names
    assert "Директор" in names


@pytest.mark.anyio
async def test_опасности_и_меры_становятся_строками(sessionmaker, monkeypatch) -> None:
    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "sp-hazards")

        hazards = {
            name
            for name in (
                await session.execute(
                    select(Hazard.name).where(Hazard.tenant_id == tenant.id)
                )
            ).scalars()
        }
        measures = {
            name
            for name in (
                await session.execute(
                    select(RiskMeasure.name).where(RiskMeasure.tenant_id == tenant.id)
                )
            ).scalars()
        }

    assert "Падение с высоты" in hazards
    assert "Наряд-допуск" in measures


@pytest.mark.anyio
async def test_должности_привязаны_к_организации_арендатора(
    sessionmaker, monkeypatch
) -> None:
    """Должность требует организацию — проверяем, что взята СВОЯ, а не чужая."""

    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "sp-company")

        rows = (
            (
                await session.execute(
                    select(Position).where(Position.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )
        own_company_ids = {
            cid
            for cid in (
                await session.execute(
                    select(Company.id).where(Company.tenant_id == tenant.id)
                )
            ).scalars()
        }

    assert rows
    assert {row.company_id for row in rows} <= own_company_ids


@pytest.mark.anyio
async def test_повторная_выдача_не_удваивает_справочник(
    sessionmaker, monkeypatch
) -> None:
    """Выдача повторяется (ретрай, повторный вызов) — второй проход не должен дублировать."""

    async with sessionmaker() as session:
        await _bootstrap(session, monkeypatch, "sp-twice")
        await _bootstrap(session, monkeypatch, "sp-twice")

        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "sp-twice"))
        ).scalar_one()
        hazards = [
            name
            for name in (
                await session.execute(
                    select(Hazard.name).where(Hazard.tenant_id == tenant.id)
                )
            ).scalars()
        ]

    assert len(hazards) == len(set(hazards))


@pytest.mark.anyio
async def test_пропуски_объявлены_а_не_замолчаны(sessionmaker, monkeypatch) -> None:
    """Половина ключей файла — перечисления в коде; молчание читалось бы как потеря."""

    async with sessionmaker() as session:
        summary, _tenant = await _bootstrap(session, monkeypatch, "sp-warnings")

    skipped = [w for w in summary.warnings if w.startswith("starter_pack_skipped:")]
    assert skipped, "пропуски обязаны попадать в отчёт с причиной"
    assert any("incident_types" in w for w in skipped)
    # У причины есть текст, а не просто имя ключа.
    assert all(len(w.split(":", 2)) == 3 and w.split(":", 2)[2] for w in skipped)


@pytest.mark.anyio
async def test_отчёт_о_наборе_больше_не_врёт(sessionmaker, monkeypatch) -> None:
    """`starter_pack created` теперь означает, что строки действительно созданы."""

    async with sessionmaker() as session:
        summary, tenant = await _bootstrap(session, monkeypatch, "sp-honest")

        count = await session.scalar(
            select(Hazard.id).where(Hazard.tenant_id == tenant.id).limit(1)
        )

    assert "starter_pack" in summary.created
    assert count is not None
