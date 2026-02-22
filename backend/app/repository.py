"""Data access helpers for templates and document jobs."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_current_tenant
from app.core.rbac_abac import actor_from_claims, apply_abac_filters
from app.models.models import (
    Company,
    Person,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.schemas.company import CompanyCreate
from app.schemas.template import TemplateCreate, TemplateVersionMetadata


def _assert_tenant_scope(session: AsyncSession, tenant_id: str | None) -> str:
    """Ensure repository operations stay within the current tenant scope."""

    session_tenant = session.info.get("tenant_id") or session.info.get("tenant")
    normalized_session_tenant = str(session_tenant) if session_tenant else None
    normalized_expected = str(tenant_id) if tenant_id is not None else None

    if normalized_expected is None:
        normalized_expected = normalized_session_tenant or get_current_tenant().slug

    if normalized_session_tenant and normalized_expected:
        if str(normalized_session_tenant) != str(normalized_expected):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Tenant mismatch for repository operation",
            )

    return normalized_expected


async def list_tenants(
    session: AsyncSession, tenant_slug: str, *, limit: int, offset: int
) -> tuple[list[Tenant], int]:
    """Return the active tenant ordered by creation time with total count."""

    scope_slug = _assert_tenant_scope(session, tenant_slug)
    base = select(Tenant).where(Tenant.slug == scope_slug)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    stmt = base.order_by(Tenant.created_at.asc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def create_company(
    session: AsyncSession, tenant_id: str, payload: CompanyCreate
) -> Company:
    """Insert a new company record for the provided tenant."""

    normalized_tenant = _assert_tenant_scope(session, tenant_id)

    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        return _clean(str(value))

    def _clean_list(values: list[str]) -> list[str]:
        return [item.strip() for item in values if isinstance(item, str) and item.strip()]

    company = Company(
        tenant_id=normalized_tenant,
        name=payload.name.strip(),
        inn=_clean(payload.inn),
        kpp=_clean(payload.kpp),
        ogrn=_clean(payload.ogrn),
        activity_type=_clean(payload.activity_type),
        okved_codes=_clean_list(payload.okved_codes),
        legal_address=_clean(payload.legal_address),
        actual_address=_clean(payload.actual_address),
        director=_clean(payload.director),
        bank_name=_clean(payload.bank_name),
        bank_bik=_clean(payload.bank_bik),
        bank_account=_clean(payload.bank_account),
        phone_numbers=_clean_list(payload.phone_numbers),
        contact_person=_clean(payload.contact_person),
        contact_phone=_clean(payload.contact_phone),
        contact_email=_clean_optional(payload.contact_email),
        email=_clean_optional(payload.email),
        logo_file_id=_clean(payload.logo_file_id),
        stamp_file_id=_clean(payload.stamp_file_id),
        work_types=_clean_list(payload.work_types),
        hazardous_factors=_clean_list(payload.hazardous_factors),
        is_hazardous_production_facility=bool(payload.is_hazardous_production_facility),
        has_dangerous_objects=bool(payload.has_dangerous_objects),
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company


async def list_companies(
    session: AsyncSession,
    tenant_id: str,
    *,
    limit: int,
    offset: int,
    claims: dict[str, object] | None = None,
    roles: list[str] | None = None,
) -> tuple[list[Company], int]:
    """Return companies for a tenant excluding soft-deleted rows."""

    normalized_tenant = _assert_tenant_scope(session, tenant_id)

    base = select(Company).where(
        Company.tenant_id == normalized_tenant,
        Company.deleted_at.is_(None),
    )
    if claims is not None:
        actor = actor_from_claims(claims, roles or [])
        base = apply_abac_filters(base, actor, Company)
    stmt = base.order_by(Company.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    total_stmt = select(func.count()).select_from(base.subquery())
    total = await session.scalar(total_stmt)
    return list(rows), int(total or 0)


async def list_persons(
    session: AsyncSession, tenant_id: str, *, limit: int, offset: int
) -> tuple[list[Person], int]:
    """Return people for a tenant with pagination."""

    normalized_tenant = _assert_tenant_scope(session, tenant_id)

    base = select(Person).where(
        Person.tenant_id == normalized_tenant,
        Person.deleted_at.is_(None),
    )
    stmt = base.order_by(Person.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    total_stmt = select(func.count()).select_from(base.subquery())
    total = await session.scalar(total_stmt)
    return list(rows), int(total or 0)


def _resolve_tenant_slug(session: AsyncSession, tenant_slug: str | None) -> str:
    slug = tenant_slug or session.info.get("tenant")
    normalized = str(slug) if slug else None
    return _assert_tenant_scope(session, normalized)


async def list_templates(
    session: AsyncSession,
    tenant_slug: str | None = None,
    *,
    limit: int = 50,
    offset: int = 0,
    with_total: bool = False,
) -> tuple[list[Template], int]:
    """Return tenant templates ordered from newest to oldest.

    When ``with_total`` is ``True`` a tuple containing both the templates and
    the total count is returned to support pagination responses.
    """

    slug = _resolve_tenant_slug(session, tenant_slug)
    base = select(Template).where(Template.tenant_id == slug)
    stmt = base.order_by(Template.created_at.desc()).offset(offset).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    total_stmt = select(func.count()).select_from(base.subquery())
    total = int(await session.scalar(total_stmt) or 0)
    if with_total:
        return rows, total
    return rows, total


async def get_template_by_name(
    session: AsyncSession, name: str, tenant_slug: str | None = None
) -> Template | None:
    """Return the template with the given name if it exists."""

    slug = _resolve_tenant_slug(session, tenant_slug)
    stmt = select(Template).where(
        Template.tenant_id == slug, Template.name == name
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def get_active_template_with_version(
    session: AsyncSession, name: str, tenant_slug: str | None = None
) -> tuple[Template, TemplateVersion] | None:
    """Return the template and its active version by name if present."""

    slug = _resolve_tenant_slug(session, tenant_slug)
    stmt = (
        select(Template, TemplateVersion)
        .join(TemplateVersion, TemplateVersion.template_id == Template.id)
        .where(
            Template.tenant_id == slug,
            Template.name == name,
            TemplateVersion.status == TemplateVersionStatus.ACTIVE,
        )
        .order_by(TemplateVersion.version.desc())
    )
    row: tuple[Template, TemplateVersion] | None = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row


def _ensure_idempotent_match(
    template: Template,
    version: TemplateVersion,
    payload: TemplateCreate,
    *,
    checksum: bytes,
) -> None:
    """Validate that an existing template matches the requested payload."""

    if template.description != payload.description:
        raise ValueError("Template with this name already exists")
    if template.metadata_json != payload.metadata:
        raise ValueError("Template with this name already exists")
    if version.checksum != checksum:
        raise ValueError("Template with this name already exists")


async def create_template(
    session: AsyncSession,
    tenant_or_payload: str | TemplateCreate,
    payload: TemplateCreate | None = None,
    *,
    storage_key: str,
    checksum: bytes,
    version_metadata: TemplateVersionMetadata | None = None,
    template_id: str | None = None,
    tenant_slug: str | None = None,
) -> TemplateVersion:
    """Create a template and its first active version."""

    if isinstance(tenant_or_payload, TemplateCreate):
        if payload is not None:
            raise TypeError("payload must not be provided twice")
        effective_payload = tenant_or_payload
        tenant_identifier: str | None = tenant_slug
    else:
        tenant_identifier = tenant_or_payload
        if payload is None:
            msg = "payload is required when tenant identifier is provided"
            raise TypeError(msg)
        effective_payload = payload
        if tenant_slug is None:
            tenant_slug = tenant_identifier

    slug = _resolve_tenant_slug(session, tenant_slug)
    tenant_identifier = tenant_identifier or slug

    existing = await get_active_template_with_version(session, effective_payload.name, slug)
    if existing:
        template, version = existing
        _ensure_idempotent_match(template, version, effective_payload, checksum=checksum)
        return version

    if version_metadata is None:
        raise ValueError("template version metadata is required to publish template")

    async def _create() -> TemplateVersion:
        template = Template(
            id=template_id,
            tenant_id=tenant_identifier,
            code=effective_payload.name,
            name=effective_payload.name,
            description=effective_payload.description,
            metadata_json=effective_payload.metadata,
            storage_key=storage_key,
        )
        session.add(template)
        await session.flush()
        await session.refresh(template)

        stmt = select(func.coalesce(func.max(TemplateVersion.version), 0)).where(
            TemplateVersion.template_id == template.id
        )
        current_version = await session.scalar(stmt)
        next_version = int(current_version or 0) + 1

        await session.execute(
            update(TemplateVersion)
            .where(
                TemplateVersion.template_id == template.id,
                TemplateVersion.status == TemplateVersionStatus.ACTIVE,
            )
            .values(status=TemplateVersionStatus.ARCHIVED)
        )

        version = TemplateVersion(
            tenant_id=slug,
            template_id=template.id,
            version=next_version,
            checksum=checksum,
            status=TemplateVersionStatus.ACTIVE,
            payload_key=storage_key,
            document_type=version_metadata.document_type,
            required_fields_schema=version_metadata.required_fields_schema,
            applicability_rules=version_metadata.applicability_rules,
            output_types=version_metadata.output_types,
            profile=version_metadata.profile,
        )
        session.add(version)
        await session.flush()
        await session.refresh(version)
        return version

    try:
        return await _create()
    except IntegrityError:
        await session.rollback()
        existing = await get_active_template_with_version(session, payload.name, slug)
        if not existing:
            raise
        template, version = existing
        _ensure_idempotent_match(template, version, payload, checksum=checksum)
        return version
