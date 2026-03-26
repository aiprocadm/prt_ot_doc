"""Development demo data bootstrap routines."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import Settings
from app.db import ensure_tenant_schema, session_scope
from app.domains.packs.seeder import ensure_default_packs
from app.models.finance import Department
from app.models.models import Company, Person, Position, Site, Tenant, TrainingCourse

logger = logging.getLogger(__name__)


async def bootstrap_demo_tenant(settings: Settings) -> None:
    """Create a deterministic tenant with baseline entities for demo walkthrough."""

    if not settings.demo_bootstrap:
        return
    if settings.app_env not in {"development", "test"}:
        logger.warning("demo.bootstrap.skipped", extra={"reason": "not-dev", "env": settings.app_env})
        return

    tenant_slug = settings.demo_tenant_id.strip() or "demo"
    company_name = settings.demo_company_name.strip() or "ООО Демо Строй"
    site_name = settings.demo_site_name.strip() or "Площадка Север"

    async with session_scope(tenant="public") as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                slug=tenant_slug,
                name=f"{company_name} ({tenant_slug})",
                contact_email="demo@example.local",
                is_active=True,
            )
            session.add(tenant)
            await session.flush()

    ensure_tenant_schema(tenant_slug)

    async with session_scope(tenant=tenant_slug) as session:
        company = (await session.execute(select(Company).where(Company.name == company_name))).scalar_one_or_none()
        if company is None:
            company = Company(tenant_id=tenant_slug, name=company_name, legal_address="г. Москва")
            session.add(company)
            await session.flush()

        site = (await session.execute(select(Site).where(Site.company_id == company.id, Site.name == site_name))).scalar_one_or_none()
        if site is None:
            site = Site(tenant_id=tenant_slug, company_id=company.id, name=site_name, address="Москва, Тестовая 1")
            session.add(site)
            await session.flush()

        department = (
            await session.execute(select(Department).where(Department.company_id == company.id, Department.name == "Производство"))
        ).scalar_one_or_none()
        if department is None:
            session.add(Department(tenant_id=tenant_slug, company_id=company.id, name="Производство", code="DEMO-PROD"))

        position = (
            await session.execute(select(Position).where(Position.company_id == company.id, Position.name == "Мастер участка"))
        ).scalar_one_or_none()
        if position is None:
            position = Position(tenant_id=tenant_slug, company_id=company.id, name="Мастер участка")
            session.add(position)
            await session.flush()

        person = (
            await session.execute(
                select(Person).where(
                    Person.company_id == company.id,
                    Person.first_name == "Иван",
                    Person.last_name == "Иванов",
                )
            )
        ).scalar_one_or_none()
        if person is None:
            session.add(
                Person(
                    tenant_id=tenant_slug,
                    company_id=company.id,
                    position_id=position.id if position else None,
                    first_name="Иван",
                    last_name="Иванов",
                    personnel_number="D-001",
                    email="ivanov@example.local",
                )
            )

        course = (
            await session.execute(select(TrainingCourse).where(TrainingCourse.title == "Вводный инструктаж (демо)"))
        ).scalar_one_or_none()
        if course is None:
            session.add(
                TrainingCourse(
                    tenant_id=tenant_slug,
                    title="Вводный инструктаж (демо)",
                    code="demo-intro",
                    duration_hours=2,
                )
            )

        await ensure_default_packs(session, tenant_slug=tenant_slug)
        logger.info("demo.bootstrap.done", extra={"tenant": tenant_slug, "company": company_name, "site": site_name})
