"""Utilities for building test data consistently across the suite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.models import (
    Company,
    Person,
    PipelineRun,
    PipelineRunStatus,
    RoleEnum,
    Site,
    Template,
    Tenant,
    User,
)
from app.services.auth import hash_password


@dataclass(slots=True)
class TestDataFactory:
    """Helper that encapsulates common persistence operations for tests."""

    sessionmaker: async_sessionmaker[AsyncSession]
    __test__ = False  # Prevent pytest from treating this helper as a test case.

    async def ensure_tenant(
        self,
        *,
        slug: str = "test",
        name: str | None = None,
        contact_email: str | None = None,
        is_active: bool = True,
        session: AsyncSession | None = None,
    ) -> Tenant:
        if session is not None:
            existing = (
                await session.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one_or_none()
            if existing:
                return existing

            tenant = Tenant(
                slug=slug,
                name=name or slug.title(),
                contact_email=contact_email or f"{slug}@example.com",
                is_active=is_active,
            )
            session.add(tenant)
            await session.flush()
            await session.refresh(tenant)
            return tenant

        async with self.sessionmaker() as new_session:
            existing = (
                await new_session.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one_or_none()
            if existing:
                return existing

            tenant = Tenant(
                slug=slug,
                name=name or slug.title(),
                contact_email=contact_email or f"{slug}@example.com",
                is_active=is_active,
            )
            new_session.add(tenant)
            await new_session.commit()
            await new_session.refresh(tenant)
            return tenant

    async def create_company(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_slug: str = "test",
        name: str = "ACME Corp",
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> Company:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        company = Company(tenant_id=tenant_obj.id, name=name, **overrides)
        return await self._save(company, session=session)

    async def create_site(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_slug: str = "test",
        company: Company | None = None,
        name: str = "Main site",
        address: str = "Test address",
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> Site:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        company_obj = company or await self.create_company(tenant=tenant_obj, session=session)
        site = Site(
            tenant_id=tenant_obj.id,
            company_id=company_obj.id,
            name=name,
            address=address,
            **overrides,
        )
        return await self._save(site, session=session)

    async def create_user(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_slug: str = "test",
        email: str | None = None,
        full_name: str | None = None,
        role: RoleEnum = RoleEnum.ADMIN,
        password: str = "secret123",
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> User:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        email_value = email or f"{role.value}-{tenant_obj.slug}@example.com"
        full_name_value = full_name or f"{role.value.title()} User"
        hashed_password = overrides.pop("hashed_password", hash_password(password))
        user = User(
            tenant_id=tenant_obj.id,
            email=email_value,
            full_name=full_name_value,
            role=role,
            hashed_password=hashed_password,
            **overrides,
        )
        return await self._save(user, session=session)

    async def create_person(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_slug: str = "test",
        company: Company | None = None,
        first_name: str = "John",
        last_name: str = "Doe",
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> Person:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        company_obj = company or await self.create_company(tenant=tenant_obj, session=session)
        person = Person(
            tenant_id=tenant_obj.id,
            company_id=company_obj.id,
            first_name=first_name,
            last_name=last_name,
            **overrides,
        )
        return await self._save(person, session=session)

    async def create_template(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_slug: str = "test",
        name: str = "Template",
        metadata: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> Template:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        template = Template(
            tenant_id=tenant_obj.id,
            name=name,
            metadata_json=metadata or {},
            **overrides,
        )
        return await self._save(template, session=session)

    async def create_document(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_id: str | None = None,
        tenant_slug: str = "test",
        template: Template | None = None,
        company: Company | None = None,
        person: Person | None = None,
        creator: User | None = None,
        status: DocumentStatus = DocumentStatus.DRAFT,
        version_payload: dict[str, Any] | None = None,
        version_file_key: str | None = None,
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> tuple[Document, DocumentVersion]:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        use_tenant_id = tenant_id if tenant_id else tenant_obj.id
        template_obj = template or await self.create_template(tenant=tenant_obj, session=session)
        company_obj = company or await self.create_company(tenant=tenant_obj, session=session)
        person_obj = person or await self.create_person(
            tenant=tenant_obj, company=company_obj, session=session
        )
        creator_obj = creator or await self.create_user(tenant=tenant_obj, session=session)
        # Ensure tenant_id is not duplicated if passed in overrides
        filtered_overrides = {k: v for k, v in overrides.items() if k != "tenant_id"}
        document = Document(
            tenant_id=use_tenant_id,
            template_id=template_obj.id,
            company_id=company_obj.id,
            person_id=person_obj.id,
            status=status,
            created_by=creator_obj.id,
            **filtered_overrides,
        )
        document, version = await self._save_document_with_version(
            document,
            version_payload or {},
            template_version=overrides.get("template_version", "v1"),
            file_key=version_file_key,
            session=session,
        )
        return document, version

    async def create_pipeline_run(
        self,
        *,
        tenant: Tenant | None = None,
        tenant_slug: str = "test",
        status: PipelineRunStatus = PipelineRunStatus.QUEUED,
        session: AsyncSession | None = None,
        **overrides: Any,
    ) -> PipelineRun:
        tenant_obj = tenant or await self.ensure_tenant(slug=tenant_slug, session=session)
        run = PipelineRun(tenant_id=tenant_obj.id, status=status, **overrides)
        return await self._save(run, session=session)

    async def _save(
        self,
        instance: Any,
        *,
        session: AsyncSession | None = None,
    ) -> Any:
        if session is not None:
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance

        async with self.sessionmaker() as new_session:
            new_session.add(instance)
            await new_session.commit()
            await new_session.refresh(instance)
            return instance

    async def _save_many(
        self,
        instances: Sequence[Any],
        *,
        session: AsyncSession | None = None,
    ) -> Sequence[Any]:
        if session is not None:
            session.add_all(instances)
            await session.commit()
            for instance in instances:
                await session.refresh(instance)
            return instances

        async with self.sessionmaker() as new_session:
            new_session.add_all(instances)
            await new_session.commit()
            for instance in instances:
                await new_session.refresh(instance)
            return instances

    async def _save_document_with_version(
        self,
        document: Document,
        payload: dict[str, Any],
        *,
        template_version: str = "v1",
        file_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[Document, DocumentVersion]:
        version = DocumentVersion(
            tenant_id=document.tenant_id,
            document=document,
            template_version=template_version,
            data_json=payload,
            file_key=file_key or f"doc-{document.id or 'new'}-v1",
        )
        await self._save_many([document, version], session=session)
        return document, version
