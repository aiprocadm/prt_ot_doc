from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, SharedBase
from app.models.models import Person, Tenant
from app.repository import (
    create_company,
    create_template,
    get_active_template_with_version,
    get_template_by_name,
    list_companies,
    list_persons,
    list_templates,
    list_tenants,
)
from app.schemas.company import CompanyCreate
from app.schemas.template import TemplateCreate, TemplateVersionMetadata


def _prepare_sqlite_metadata() -> None:
    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in Base.metadata.tables:
        Tenant.__table__.tometadata(Base.metadata, schema=None)


async def _setup_engine():
    _prepare_sqlite_metadata()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        tenant_a = Tenant(slug="alpha", name="Alpha", contact_email="alpha@example.com")
        tenant_b = Tenant(slug="beta", name="Beta", contact_email="beta@example.com")
        session.add_all([tenant_a, tenant_b])
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        return engine, session_factory, tenant_a, tenant_b


@pytest.mark.asyncio
async def test_create_and_list_companies() -> None:
    engine, session_factory, tenant_a, tenant_b = await _setup_engine()

    async with session_factory() as session:
        company = await create_company(
            session,
            tenant_a.id,
            CompanyCreate(
                name="Alpha LLC",
                inn="7701000000",
                kpp="770101001",
                ogrn="1027700132195",
                legal_address="Moscow",
                actual_address="Mytishchi",
                director="Ivan Ivanov",
                bank_name="Sberbank",
                bank_bik="044525225",
                bank_account="40702810900000000001",
                phone_numbers=["+7 999 111-22-33", "8 (495) 123-45-67"],
                email="info@alpha.ru",
                work_types=["Construction", "Maintenance"],
                hazardous_factors=["Noise", "Vibration"],
            ),
        )
        assert company.tenant_id == tenant_a.id
        assert company.inn == "7701000000"
        assert company.phone_numbers == ["+7 999 111-22-33", "8 (495) 123-45-67"]
        await session.commit()

    async with session_factory() as session:
        companies, total = await list_companies(session, tenant_a.id, limit=10, offset=0)
        assert total == 1
        assert companies[0].name == "Alpha LLC"
        assert companies[0].inn == "7701000000"

        other_companies, other_total = await list_companies(
            session, tenant_b.id, limit=10, offset=0
        )
        assert other_total == 0
        assert other_companies == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_tenants_returns_sorted_total() -> None:
    engine, session_factory, *_ = await _setup_engine()

    async with session_factory() as session:
        tenants, total = await list_tenants(session, "alpha", limit=10, offset=0)
        assert total == 1
        assert [tenant.slug for tenant in tenants] == ["alpha"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_persons_excludes_soft_deleted_rows() -> None:
    engine, session_factory, tenant_a, _ = await _setup_engine()

    async with session_factory() as session:
        company = await create_company(
            session,
            tenant_a.id,
            CompanyCreate(
                name="Alpha LLC",
                inn="7701000000",
                kpp="770101001",
                ogrn="1027700132195",
                legal_address="Moscow",
                actual_address="Mytishchi",
                director="Ivan Ivanov",
                bank_name="Sberbank",
                bank_bik="044525225",
                bank_account="40702810900000000001",
                phone_numbers=["+7 999 111-22-33"],
                email="info@alpha.ru",
                work_types=["Construction"],
                hazardous_factors=[],
            ),
        )
        active = Person(
            tenant_id=tenant_a.id,
            company_id=company.id,
            first_name="Alice",
            last_name="Active",
            qualifications=[],
            current_ppe=[],
        )
        archived = Person(
            tenant_id=tenant_a.id,
            company_id=company.id,
            first_name="Bob",
            last_name="Deleted",
            qualifications=[],
            current_ppe=[],
            deleted_at=datetime.now(tz=timezone.utc),
        )
        session.add_all([active, archived])
        await session.commit()

    async with session_factory() as session:
        people, total = await list_persons(session, tenant_a.id, limit=10, offset=0)
        assert total == 1
        assert len(people) == 1
        assert people[0].last_name == "Active"

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_persons_q_search_typeahead() -> None:
    """Срез-4: серверный поиск по подстроке ФИО / таб. номеру (без регистра)."""
    engine, session_factory, tenant_a, tenant_b = await _setup_engine()

    async with session_factory() as session:
        company = await create_company(
            session,
            tenant_a.id,
            CompanyCreate(
                name="Alpha LLC",
                inn="7701000000",
                kpp="770101001",
                ogrn="1027700132195",
                legal_address="Moscow",
                actual_address="Mytishchi",
                director="Ivan Ivanov",
                bank_name="Sberbank",
                bank_bik="044525225",
                bank_account="40702810900000000001",
                phone_numbers=["+7 999 111-22-33"],
                email="info@alpha.ru",
                work_types=["Construction"],
                hazardous_factors=[],
            ),
        )
        session.add_all(
            [
                Person(
                    tenant_id=tenant_a.id,
                    company_id=company.id,
                    first_name="Иван",
                    last_name="Иванов",
                    middle_name="Иванович",
                    personnel_number="TAB-100",
                    qualifications=[],
                    current_ppe=[],
                ),
                Person(
                    tenant_id=tenant_a.id,
                    company_id=company.id,
                    first_name="Пётр",
                    last_name="Петров",
                    qualifications=[],
                    current_ppe=[],
                ),
                Person(
                    tenant_id=tenant_b.id,
                    company_id=company.id,
                    first_name="Иван",
                    last_name="Чужой",
                    qualifications=[],
                    current_ppe=[],
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        # подстрока фамилии; для кириллицы регистронезависимость даёт PG ILIKE,
        # SQLite lower() умеет только ASCII — потому здесь подстрока без смены регистра
        people, total = await list_persons(session, tenant_a.id, limit=10, offset=0, q="ванов")
        assert total == 1
        assert people[0].last_name == "Иванов"
        # табельный номер
        people, total = await list_persons(session, tenant_a.id, limit=10, offset=0, q="tab-1")
        assert total == 1 and people[0].personnel_number == "TAB-100"
        # имя ищется тоже, но чужой арендатор не виден
        people, total = await list_persons(session, tenant_a.id, limit=10, offset=0, q="Иван")
        assert total == 1
        # пустая строка = без фильтра
        _, total = await list_persons(session, tenant_a.id, limit=10, offset=0, q="  ")
        assert total == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_templates_scoped_by_tenant() -> None:
    engine, session_factory, tenant_a, tenant_b = await _setup_engine()

    payload = TemplateCreate(name="Safety Plan", description=None, metadata={})
    version_metadata = TemplateVersionMetadata(
        document_type="safety_plan",
        required_fields_schema={"type": "object", "properties": {}},
        applicability_rules={},
        output_types=["docx", "pdf"],
        profile={},
    )
    checksum = b"checksum"

    async with session_factory() as session:
        await create_template(
            session,
            tenant_a.id,
            payload,
            storage_key=f"{tenant_a.slug}/templates/template.docx",
            checksum=checksum,
            version_metadata=version_metadata,
        )
        await session.commit()

    async with session_factory() as session:
        templates_a, total_a = await list_templates(session, tenant_a.id, limit=10, offset=0)
        assert total_a == 1
        assert templates_a[0].tenant_id == tenant_a.id

        templates_b, total_b = await list_templates(session, tenant_b.id, limit=10, offset=0)
        assert total_b == 0
        assert templates_b == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_template_helpers_and_idempotency() -> None:
    engine, session_factory, tenant_a, _ = await _setup_engine()

    payload = TemplateCreate(name="Safety Plan", description="Plan", metadata={"key": "value"})
    version_metadata = TemplateVersionMetadata(
        document_type="safety_plan",
        required_fields_schema={"type": "object", "properties": {}},
        applicability_rules={},
        output_types=["docx", "pdf"],
        profile={},
    )
    checksum = b"checksum"

    async with session_factory() as session:
        version = await create_template(
            session,
            tenant_a.id,
            payload,
            storage_key=f"{tenant_a.slug}/templates/template.docx",
            checksum=checksum,
            version_metadata=version_metadata,
        )
        await session.commit()

    async with session_factory() as session:
        template = await get_template_by_name(session, payload.name, tenant_slug=tenant_a.id)
        assert template is not None
        helper_result = await get_active_template_with_version(
            session, payload.name, tenant_slug=tenant_a.id
        )
        assert helper_result is not None
        helper_template, helper_version = helper_result
        assert helper_template.id == template.id
        assert helper_version.id == version.id

        reused = await create_template(
            session,
            tenant_a.id,
            payload,
            storage_key=f"{tenant_a.slug}/templates/template.docx",
            checksum=checksum,
            version_metadata=version_metadata,
        )
        assert reused.id == version.id

        with pytest.raises(ValueError):
            await create_template(
                session,
                tenant_a.id,
                TemplateCreate(name=payload.name, description="Other", metadata={}),
                storage_key=f"{tenant_a.slug}/templates/another.docx",
                checksum=b"other",
                version_metadata=version_metadata,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_template_requires_payload_with_explicit_tenant() -> None:
    engine, session_factory, tenant_a, _ = await _setup_engine()

    async with session_factory() as session:
        with pytest.raises(TypeError):
            await create_template(
                session,
                tenant_a.id,
                None,
                storage_key=f"{tenant_a.slug}/templates/missing.docx",
                checksum=b"checksum",
            )

    await engine.dispose()
