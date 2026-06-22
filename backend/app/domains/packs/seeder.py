"""Utilities for provisioning default document packs and templates."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import tenant_prefix_path
from app.domains.packs.definitions import (
    DEFAULT_PACKS,
    DOCX_MIME,
    PACK_DEFINITIONS_BY_CODE,
    PackDefinition,
    PackTemplateSpec,
)
from app.models.models import (
    DocumentPack,
    DocumentPackItem,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.repository import create_template, get_active_template_with_version
from app.schemas.template import TemplateCreate, TemplateVersionMetadata
from app.services.file_storage import FileStorageService

__all__ = ["ensure_default_packs", "ensure_pack_by_code"]


async def _resolve_tenant_id(session: AsyncSession, tenant_slug: str) -> str:
    info = getattr(session, "info", None)
    if isinstance(info, dict):
        session_tenant_slug = (
            str(info.get("tenant_slug") or info.get("tenant") or "").strip().lower()
        )
        session_tenant_id = str(info.get("tenant_id") or "").strip()
        if session_tenant_slug == tenant_slug and session_tenant_id:
            return session_tenant_id

    tenant = (
        await session.execute(select(Tenant.id).where(Tenant.slug == tenant_slug).limit(1))
    ).scalar_one_or_none()
    if tenant is None:
        raise ValueError(f"Tenant not found for slug {tenant_slug}")
    return str(tenant)


async def _ensure_template(
    session: AsyncSession,
    *,
    tenant_slug: str,
    pack: PackDefinition,
    template_spec: PackTemplateSpec,
    storage: FileStorageService,
) -> Template:
    key = f"{tenant_prefix_path(tenant_slug)}/templates/{template_spec.code}.docx"
    payload_bytes = template_spec.builder()
    storage.put(key, payload_bytes, content_type=DOCX_MIME)

    checksum = hashlib.sha256(payload_bytes).digest()
    payload = TemplateCreate(
        name=template_spec.code,
        description=template_spec.description,
        metadata={
            "pack_code": pack.code,
            "display_name": template_spec.name,
            "category": template_spec.category,
        },
    )
    version_metadata = TemplateVersionMetadata(
        document_type=template_spec.category or template_spec.code,
        required_fields_schema={"type": "object", "properties": {}, "additionalProperties": True},
        applicability_rules={},
        output_types=["docx", "pdf"],
        profile={},
    )

    try:
        version = await create_template(
            session,
            tenant_slug,
            payload,
            storage_key=key,
            checksum=checksum,
            version_metadata=version_metadata,
            tenant_slug=tenant_slug,
        )
    except ValueError as exc:
        # Re-runs after partial seed or non-deterministic DOCX bytes: reuse existing template.
        if str(exc) != "Template with this name already exists":
            raise
        existing = await get_active_template_with_version(session, template_spec.code, tenant_slug)
        if existing is None:
            raise
        template, _version = existing
        return template

    template = await session.get(Template, version.template_id)
    if template is None:  # pragma: no cover - defensive
        raise RuntimeError(
            f"Template {template_spec.code} was not persisted for tenant {tenant_slug}"
        )
    return template


async def _ensure_pack(
    session: AsyncSession,
    *,
    tenant_slug: str,
    definition: PackDefinition,
    templates: dict[str, Template],
) -> DocumentPack:
    tenant_id = await _resolve_tenant_id(session, tenant_slug)
    stmt = select(DocumentPack).where(
        DocumentPack.tenant_id.in_((tenant_id, tenant_slug)),
        DocumentPack.code == definition.code,
        DocumentPack.deleted_at.is_(None),
    )
    pack = (await session.execute(stmt)).scalar_one_or_none()
    if pack is None:
        pack = DocumentPack(
            tenant_id=tenant_id,
            code=definition.code,
            name=definition.name,
            description=definition.description,
            is_active=True,
            module=definition.module,
            scenario_type=definition.scenario_type,
        )
        session.add(pack)
        await session.flush()
    else:
        pack.name = definition.name
        pack.description = definition.description
        pack.is_active = True
        pack.module = definition.module
        pack.scenario_type = definition.scenario_type

    stmt_items = select(DocumentPackItem).where(
        DocumentPackItem.pack_id == pack.id,
        DocumentPackItem.deleted_at.is_(None),
    )
    existing_items = {
        item.template_id: item for item in (await session.execute(stmt_items)).scalars().all()
    }

    async def _resolve_template_version_id(template: Template) -> str:
        stmt = (
            select(TemplateVersion)
            .where(
                TemplateVersion.template_id == template.id,
                TemplateVersion.status == TemplateVersionStatus.ACTIVE,
            )
            .order_by(TemplateVersion.version.desc())
            .limit(1)
        )
        version = (await session.execute(stmt)).scalar_one_or_none()
        if version is None:
            raise ValueError(f"Template {template.name} has no active version")
        return version.id

    for position, template_code in enumerate(definition.item_order, start=1):
        template = templates[template_code]
        item = existing_items.get(template.id)
        if item is None:
            version_id = await _resolve_template_version_id(template)
            item = DocumentPackItem(
                tenant_id=tenant_id,
                pack_id=pack.id,
                template_id=template.id,
                template_version_id=version_id,
                order=position,
                required=True,
                condition={},
            )
            session.add(item)
        else:
            item.order = position
            item.required = True
            item.condition = item.condition or {}
            if item.template_version_id is None:
                item.template_version_id = await _resolve_template_version_id(template)
    return pack


async def _materialize_pack(
    session: AsyncSession,
    *,
    tenant_slug: str,
    definition: PackDefinition,
    storage: FileStorageService,
) -> None:
    templates: dict[str, Template] = {}
    for template_spec in definition.templates:
        template = await _ensure_template(
            session,
            tenant_slug=tenant_slug,
            pack=definition,
            template_spec=template_spec,
            storage=storage,
        )
        templates[template_spec.code] = template
    await _ensure_pack(
        session,
        tenant_slug=tenant_slug,
        definition=definition,
        templates=templates,
    )


async def ensure_default_packs(
    session: AsyncSession,
    *,
    tenant_slug: str,
) -> None:
    """Create default document packs for ``tenant_slug`` when missing."""

    storage = FileStorageService.default()
    for definition in DEFAULT_PACKS:
        await _materialize_pack(
            session,
            tenant_slug=tenant_slug,
            definition=definition,
            storage=storage,
        )


async def ensure_pack_by_code(
    session: AsyncSession,
    *,
    tenant_slug: str,
    pack_code: str,
) -> DocumentPack:
    """Create a document pack for a specific scenario if missing."""

    definition = PACK_DEFINITIONS_BY_CODE.get(pack_code)
    if definition is None:
        raise ValueError(f"Unknown pack code: {pack_code}")

    storage = FileStorageService.default()
    await _materialize_pack(
        session,
        tenant_slug=tenant_slug,
        definition=definition,
        storage=storage,
    )

    tenant_id = await _resolve_tenant_id(session, tenant_slug)
    stmt = select(DocumentPack).where(
        DocumentPack.tenant_id.in_((tenant_id, tenant_slug)),
        DocumentPack.code == pack_code,
        DocumentPack.deleted_at.is_(None),
    )
    pack = (await session.execute(stmt)).scalar_one()
    return pack
