"""Document-pack endpoints — shared foundation (ARCH-4 slice 8 split).

The single ``router`` + logger, access dependencies, role constants, error helpers and
all pack helper functions shared by the management and run endpoint modules.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    Person,
    Site,
    Tenant,
)
from app.modules.packs.context import enrich_context
from app.modules.packs.seeder import ensure_default_packs
from app.schemas.pack import (
    PackGenerateRequest,
    PackListItem,
    PackRunRequest,
    PackScenarioDescriptor,
    PackScenarioTemplate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _pack_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(
            code="PACK_VALIDATION_ERROR", message=message, error_type="packs"
        ),
    )


def _pack_not_found(*, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(code=code, message=message, error_type="packs"),
    )


def _pack_conflict(
    message: str,
    *,
    code: str = "PACK_CONFLICT",
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(code=code, message=message, error_type="packs", details=details),
    )


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_PACK_READ_ROLES = ["admin", "employee", "client_admin", "client_user"]
_PACK_WRITE_ROLES = ["admin", "employee", "client_admin"]

PackReadAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_PACK_READ_ROLES,
            action="read pack",
        )
    ),
]


PackWriteAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_PACK_WRITE_ROLES,
            action="manage pack",
        )
    ),
]


_SINGLE_TASK_PLANS: frozenset[str] = frozenset({"start"})


def _validate_pack_output_selection(include_docx: bool, include_pdf: bool) -> None:
    if not (include_docx or include_pdf):
        raise _pack_bad_request("At least one of include_docx or include_pdf must be enabled")


def _resolve_tenant_plan(tenant: Tenant) -> str | None:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    if not isinstance(settings, dict):
        return None
    plan = settings.get("plan") or settings.get("billing_plan")
    billing_settings = settings.get("billing")
    if plan is None and isinstance(billing_settings, dict):
        plan = billing_settings.get("plan")
    if plan is None:
        return None
    normalized = str(plan).strip().lower()
    return normalized or None


def _has_single_task_limit(tenant: Tenant) -> bool:
    plan = _resolve_tenant_plan(tenant)
    if plan is None:
        return False
    return plan in _SINGLE_TASK_PLANS


def _tenant_scope_values(tenant: Tenant) -> tuple[str, ...]:
    values: set[str] = {tenant.slug}
    if tenant.id:
        values.add(str(tenant.id))
    return tuple(values)


def _pack_to_list_item(pack: DocumentPack) -> PackListItem:
    mod = pack.module.value if hasattr(pack.module, "value") else str(pack.module)
    scen = (
        pack.scenario_type.value
        if hasattr(pack.scenario_type, "value")
        else str(pack.scenario_type)
    )
    return PackListItem(
        id=pack.id,
        code=pack.code,
        name=pack.name,
        description=pack.description,
        module=mod,
        scenario_type=scen,
        is_active=pack.is_active,
        created_at=pack.created_at,
        updated_at=pack.updated_at,
    )


def _serialize_definition(definition) -> PackScenarioDescriptor:  # type: ignore[override]
    return PackScenarioDescriptor(
        code=definition.code,
        name=definition.name,
        description=definition.description,
        scenario=definition.scenario.value,
        module=(
            definition.module.value
            if hasattr(definition.module, "value")
            else str(definition.module)
        ),
        scenario_type=(
            definition.scenario_type.value
            if hasattr(definition.scenario_type, "value")
            else str(definition.scenario_type)
        ),
        templates=[
            PackScenarioTemplate(
                code=template.code,
                name=template.name,
                category=template.category,
            )
            for template in definition.templates
        ],
    )


async def _get_company(
    session: AsyncSession,
    tenant: Tenant,
    company_id: str,
    *,
    access: AccessContext | None = None,
) -> Company:
    tenant_scope = _tenant_scope_values(tenant)
    stmt = select(Company).where(
        Company.id == company_id,
        Company.deleted_at.is_(None),
        Company.tenant_id.in_(tenant_scope),
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise _pack_not_found(code="PACK_COMPANY_NOT_FOUND", message="Company not found")
    if access is not None and access.role in {"client_admin", "client_user"}:
        access.ensure_company_access(company.id, action="access company data")
    return company


async def _get_site(
    session: AsyncSession, tenant: Tenant, company: Company, site_id: str | None
) -> Site | None:
    if site_id is None:
        return None
    tenant_scope = _tenant_scope_values(tenant)
    stmt = select(Site).where(
        Site.id == site_id,
        Site.deleted_at.is_(None),
        Site.tenant_id.in_(tenant_scope),
    )
    site = (await session.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise _pack_not_found(code="PACK_SITE_NOT_FOUND", message="Site not found")
    if site.company_id != company.id:
        raise _pack_bad_request("Site does not belong to company")
    return site


async def _get_persons(
    session: AsyncSession,
    tenant: Tenant,
    company: Company,
    person_ids: Iterable[str],
) -> list[Person]:
    ids = [pid for pid in person_ids if pid]
    if not ids:
        return []
    unique_ids: list[str] = []
    seen = set()
    for pid in ids:
        if pid not in seen:
            unique_ids.append(pid)
            seen.add(pid)
    tenant_scope = _tenant_scope_values(tenant)
    stmt = select(Person).where(
        Person.id.in_(unique_ids),
        Person.deleted_at.is_(None),
        Person.tenant_id.in_(tenant_scope),
    )
    rows = (await session.execute(stmt)).scalars().all()
    persons = list(rows)
    if len(persons) != len(unique_ids):
        raise _pack_not_found(
            code="PACK_PERSONS_NOT_FOUND",
            message="One or more persons were not found",
        )
    indexed = {person.id: person for person in persons}
    ordered = []
    for pid in unique_ids:
        person = indexed[pid]
        if person.company_id != company.id:
            raise _pack_bad_request("Person does not belong to the specified company")
        ordered.append(person)
    return ordered


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _enforce_person_invariants(
    session: AsyncSession, tenant: Tenant, persons: list[Person]
) -> None:
    from app.services.person_admission import enforce_person_admission

    tenant_scope = _tenant_scope_values(tenant)
    try:
        await enforce_person_admission(session, tenant_scope=tenant_scope, persons=persons)
    except ValueError as exc:
        payload = exc.args[0] if exc.args else {}
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "requirements_not_met",
                "error_code": "requirements_not_met",
                "message": "Pack prerequisites are not satisfied for one or more persons",
                "type": "packs",
                "details": payload.get("details", []) if isinstance(payload, dict) else [],
            },
        ) from exc


async def _get_pack(session: AsyncSession, tenant: Tenant, pack_code: str) -> DocumentPack:
    await ensure_default_packs(session, tenant_slug=tenant.slug)
    tenant_scope = _tenant_scope_values(tenant)
    stmt = (
        select(DocumentPack)
        .options(
            selectinload(DocumentPack.items).selectinload(DocumentPackItem.template),
            selectinload(DocumentPack.items).selectinload(DocumentPackItem.template_version),
        )
        .where(
            DocumentPack.code == pack_code,
            DocumentPack.tenant_id.in_(tenant_scope),
            DocumentPack.is_active.is_(True),
            DocumentPack.deleted_at.is_(None),
        )
    )
    pack = (await session.execute(stmt)).scalar_one_or_none()
    if pack is None:
        raise _pack_not_found(code="PACK_NOT_FOUND", message="Pack not found")
    if not pack.items:
        raise _pack_conflict("Pack contains no items", code="PACK_EMPTY")
    return pack


def _build_context(
    *,
    pack: DocumentPack,
    company: Company,
    site: Site | None,
    person: Person | None,
    payload: PackRunRequest,
) -> dict[str, object]:
    company_payload = {
        "id": company.id,
        "name": company.name,
        "tax_id": company.tax_id,
        "address": company.address,
        "inn": company.tax_id,
    }
    context: dict[str, object] = {
        "pack_code": pack.code,
        "company": company_payload,
        "data": dict(payload.data),
    }
    if site is not None:
        context["site"] = {
            "id": site.id,
            "name": site.name,
            "address": site.address,
        }
    if person is not None:
        context["person"] = {
            "id": person.id,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "middle_name": person.middle_name,
            "company_id": person.company_id,
            "position_id": person.position_id,
            "personnel_number": person.personnel_number,
            "hired_at": person.hired_at.isoformat() if person.hired_at else None,
            "qualifications": list(person.qualifications or []),
            "snils": person.snils,
            "passport": person.passport,
            "current_ppe": list(person.current_ppe or []),
        }
    return enrich_context(pack.code, context, dict(payload.data))


def _coerce_string(value: object | None, default: str) -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result or default


def _resolve_naming(
    payload: PackGenerateRequest, company: Company, site: Site | None, pack: DocumentPack
) -> dict[str, object]:
    config = payload.naming
    org = _coerce_string(config.org, company.name)
    unit = _coerce_string(config.unit, site.name if site else "hq")
    project = _coerce_string(
        config.project, payload.data.get("project") if payload.data else pack.code
    )
    client = _coerce_string(config.client, company.name)
    topic = _coerce_string(config.topic, pack.code)
    version = config.version or 1
    reference_date = config.reference_date or date.today()
    flags: list[str] = []
    flags.extend(config.flags)
    data_flags = payload.data.get("flags") if payload.data else None
    if isinstance(data_flags, list):
        for flag in data_flags:
            if isinstance(flag, str) and flag.strip():
                flags.append(flag.strip())
    deduplicated_flags = tuple(dict.fromkeys(flags))
    return {
        "org": org,
        "unit": unit,
        "project": project,
        "client": client,
        "topic": topic,
        "version": version,
        "reference_date": reference_date,
        "flags": deduplicated_flags,
    }
