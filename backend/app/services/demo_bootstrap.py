"""Development demo data bootstrap routines."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import Settings
from app.db import aensure_tenant_schema, session_scope
from app.domains.packs.seeder import ensure_default_packs
from app.models.feature import Feature
from app.models.finance import Department
from app.models.models import Company, MedicalExamKind, MedicalNorm, Person, Position, Site, Tenant, TrainingCourse
from app.modules.contractors.models import ComplianceStatus, ContractorEmployee, ContractorRegistry

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
                code=tenant_slug,
                name=f"{company_name} ({tenant_slug})",
                contact_email="demo@example.local",
                schema_name=f"tenant_{tenant_slug}",
                is_active=True,
            )
            session.add(tenant)
            await session.flush()
        tenant_db_id = str(tenant.id)
        tenant_schema_name = str(tenant.schema_name or f"tenant_{tenant_slug}")

        # Seed shared Feature catalogue row for medical (idempotent).
        medical_feature = (
            await session.execute(select(Feature).where(Feature.code == "medical"))
        ).scalar_one_or_none()
        if medical_feature is None:
            session.add(Feature(code="medical", title="Медосмотры"))
            await session.flush()

        # Seed shared Feature catalogue row for contractors (idempotent).
        contractors_feature = (
            await session.execute(select(Feature).where(Feature.code == "contractors"))
        ).scalar_one_or_none()
        if contractors_feature is None:
            session.add(Feature(code="contractors", title="Подрядчики"))
            await session.flush()

    await aensure_tenant_schema(tenant_slug, schema_name=tenant_schema_name)

    # Pass schema_name explicitly: when DEFAULT_TENANT_SLUG=demo (CI default),
    # session_scope(tenant="demo") would otherwise short-circuit to the shared
    # schema and read training_course from public instead of tenant_demo.
    async with session_scope(tenant=tenant_slug, schema_name=tenant_schema_name) as session:
        company = (await session.execute(select(Company).where(Company.name == company_name))).scalar_one_or_none()
        if company is None:
            company = Company(tenant_id=tenant_db_id, name=company_name, legal_address="г. Москва")
            session.add(company)
            await session.flush()

        site = (await session.execute(select(Site).where(Site.company_id == company.id, Site.name == site_name))).scalar_one_or_none()
        if site is None:
            site = Site(tenant_id=tenant_db_id, company_id=company.id, name=site_name, address="Москва, Тестовая 1")
            session.add(site)
            await session.flush()

        department = (
            await session.execute(select(Department).where(Department.company_id == company.id, Department.name == "Производство"))
        ).scalar_one_or_none()
        if department is None:
            session.add(Department(tenant_id=tenant_db_id, company_id=company.id, name="Производство", code="DEMO-PROD"))

        position = (
            await session.execute(select(Position).where(Position.company_id == company.id, Position.name == "Мастер участка"))
        ).scalar_one_or_none()
        if position is None:
            position = Position(tenant_id=tenant_db_id, company_id=company.id, name="Мастер участка")
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
                    tenant_id=tenant_db_id,
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
                    tenant_id=tenant_db_id,
                    title="Вводный инструктаж (демо)",
                    code="demo-intro",
                    duration_hours=2,
                )
            )

        # Seed a MedicalNorm for periodic exam on the demo Position (idempotent).
        # This ensures the demo contingent list shows a "missing" row so the
        # /medical/contingent endpoint is non-empty out-of-the-box.
        if position is not None:
            existing_norm = (
                await session.execute(
                    select(MedicalNorm).where(
                        MedicalNorm.position_id == position.id,
                        MedicalNorm.exam_kind == MedicalExamKind.PERIODIC,
                    )
                )
            ).scalar_one_or_none()
            if existing_norm is None:
                session.add(
                    MedicalNorm(
                        tenant_id=tenant_db_id,
                        position_id=position.id,
                        exam_kind=MedicalExamKind.PERIODIC,
                        interval_days=365,
                    )
                )

        # Seed a demo ContractorRegistry + 2 ContractorEmployee rows (idempotent).
        demo_contractor_name = "Демо-подрядчик"
        contractor = (
            await session.execute(
                select(ContractorRegistry).where(
                    ContractorRegistry.tenant_id == tenant_db_id,
                    ContractorRegistry.name == demo_contractor_name,
                )
            )
        ).scalar_one_or_none()
        if contractor is None:
            contractor = ContractorRegistry(
                tenant_id=tenant_db_id,
                name=demo_contractor_name,
                status="active",
            )
            session.add(contractor)
            await session.flush()

            now = datetime.now(timezone.utc)
            session.add(
                ContractorEmployee(
                    tenant_id=tenant_db_id,
                    contractor_id=contractor.id,
                    full_name="Готовый Иван",
                    access_status=ComplianceStatus.VALID,
                    training_status=ComplianceStatus.VALID,
                    medical_status=ComplianceStatus.VALID,
                    last_training_at=now,
                    next_medical_at=now + timedelta(days=200),
                )
            )
            session.add(
                ContractorEmployee(
                    tenant_id=tenant_db_id,
                    contractor_id=contractor.id,
                    full_name="Просроченный Пётр",
                    access_status=ComplianceStatus.VALID,
                    training_status=ComplianceStatus.VALID,
                    medical_status=ComplianceStatus.VALID,
                    last_training_at=now,
                    next_medical_at=now - timedelta(days=1),
                )
            )

        await ensure_default_packs(session, tenant_slug=tenant_slug)
        logger.info("demo.bootstrap.done", extra={"tenant": tenant_slug, "company": company_name, "site": site_name})
