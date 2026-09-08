"""Document builders: контингент (position-level) + поименный список (person-level)."""

from datetime import date

import pytest

from app.domains.medical.service import build_contingent_register, build_named_list
from app.models.master_data import EmploymentStatus
from app.models.models import MedicalFactor, Position, PositionHazardLink
from app.models.risk import RiskHazard


async def _seed(session, data_factory):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session)
    hazard = RiskHazard(tenant_id=tenant.id, code="noise", title="Шум", medical_factor_code="4.4")
    session.add(hazard)
    await session.flush()
    pos = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
    session.add(pos)
    await session.flush()
    session.add(PositionHazardLink(tenant_id=tenant.id, position_id=pos.id, hazard_id=hazard.id))
    await data_factory.create_person(
        tenant=tenant,
        company=company,
        session=session,
        position_id=pos.id,
        first_name="Иван",
        last_name="Петров",
    )
    session.add(
        MedicalFactor(
            tenant_id=tenant.id,
            code="4.4",
            name="Шум",
            exam_kinds=["periodic"],
            periodicity_months=12,
        )
    )
    await session.commit()
    return str(tenant.id), pos.id


@pytest.mark.asyncio
async def test_contingent_register_groups_by_position_with_headcount(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id, pos_id = await _seed(session, data_factory)
        rows = await build_contingent_register(
            session, tenant_id=tenant_id, today=date(2026, 6, 13)
        )
    assert len(rows) == 1
    row = rows[0]
    assert row["position_id"] == pos_id
    assert row["headcount"] == 1
    assert {"code": "4.4", "name": "Шум"} in row["factors"]
    assert "periodic" in row["exam_kinds"]


@pytest.mark.asyncio
async def test_named_list_lists_person_with_factors_and_status(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id, _pos = await _seed(session, data_factory)
        rows = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert len(rows) == 1
    row = rows[0]
    assert row["full_name"] == "Петров Иван"
    assert row["position_name"] == "Сварщик"
    assert {"code": "4.4", "name": "Шум"} in row["factors"]
    assert row["status"] == "missing"
    assert row["next_due_date"] == date(2026, 6, 13)


@pytest.mark.asyncio
async def test_documents_empty_without_factor_mapping(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)
        reg = await build_contingent_register(session, tenant_id=tenant_id, today=date(2026, 6, 13))
        named = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert reg == [] and named == []


@pytest.mark.asyncio
async def test_отпускник_и_отстранённый_в_документах_29н_остаются(sessionmaker, data_factory):
    """«Уволенный не в счёт» — но только уволенный (срез-114).

    До среза документы 29н отбирали ``employment_status == ACTIVE``, и из
    поимённого списка молча выпадали люди В ОТПУСКЕ и ОТСТРАНЁННЫЕ. Отпускник
    обязан пройти периодический осмотр, а отстранён человек часто ровно из-за
    непройденного медосмотра: спрятать его в документе о медосмотрах значит
    спрятать саму проблему. Теперь условие общее — не удалён и не уволен.
    """

    async with sessionmaker() as session:
        tenant_id, pos_id = await _seed(session, data_factory)
        tenant = await data_factory.ensure_tenant(session=session)
        # Компания у арендатора уникальна по имени: `_seed` уже завёл «ACME
        # Corp», поэтому здесь берём вторую с явным названием.
        company = await data_factory.create_company(
            tenant=tenant, name="ACME Corp 114", session=session
        )
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos_id,
            last_name="Отпускник",
            employment_status=EmploymentStatus.ON_LEAVE,
        )
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos_id,
            last_name="Отстранён",
            employment_status=EmploymentStatus.SUSPENDED,
        )
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos_id,
            last_name="Уволен",
            employment_status=EmploymentStatus.TERMINATED,
        )
        await session.commit()

        named = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
        register = await build_contingent_register(
            session, tenant_id=tenant_id, today=date(2026, 6, 13)
        )

    surnames = {row["full_name"].split()[0] for row in named}
    assert "Отпускник" in surnames, named
    assert "Отстранён" in surnames, named
    assert "Уволен" not in surnames, named
    # Численность в «контингенте» считается тем же правилом: трое работающих.
    assert register[0]["headcount"] == 3, register

