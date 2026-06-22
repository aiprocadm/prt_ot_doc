from __future__ import annotations

import logging
import uuid
import zipfile
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Annotated, Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.idempotency import compute_request_hash
from app.core.query import (
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    FilterQuery,
    PageQuery,
    SortQuery,
    pagination_meta,
)
from app.core.response import list_response
from app.core.security import AccessContext, abac
from app.core.tenant import tenant_prefix_path
from app.core.tenant_validation import TenantContextValidator
from app.core.tracing import get_trace_id
from app.domains.files import s3
from app.domains.packs.context import enrich_context
from app.domains.packs.definitions import DEFAULT_PACKS, PACK_DEFINITIONS_BY_CODE
from app.domains.packs.seeder import ensure_default_packs, ensure_pack_by_code
from app.models.file import File as StoredFile
from app.models.file import FileScanStatus
from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    Person,
    PipelineRun,
    PipelineRunStatus,
    Site,
    TemplateVersion,
    Tenant,
)
from app.models.safety_core import RiskMapItem, SafetyRiskMap
from app.modules.ppe.services import PackSafetySummaryService
from app.schemas.pack import (
    PackFromScenarioRequest,
    PackGenerateRequest,
    PackListItem,
    PackListResponse,
    PackRunRequest,
    PackRunResponse,
    PackRunTask,
    PackScenarioDescriptor,
    PackScenarioListResponse,
    PackScenarioTemplate,
)
from app.schemas.task import TaskAcceptedResponse
from app.services.audit import AuditService
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.package_pipeline import build_idempotency_key
from app.services.pipeline import PipelineService
from app.services.tasks import generate_document_task, generate_pack_task

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


@router.get("/scenarios", response_model=PackScenarioListResponse)
async def list_pack_scenarios(access: PackReadAccess) -> PackScenarioListResponse:
    _ = access
    items = [_serialize_definition(definition) for definition in DEFAULT_PACKS]
    payload = [item.model_dump(mode="json") for item in items]
    return PackScenarioListResponse(data=payload)


@router.post(
    "/scenarios/{scenario_code}",
    response_model=PackListItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_pack_from_scenario(
    scenario_code: str,
    payload: PackFromScenarioRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: PackWriteAccess,
) -> PackListItem:
    TenantContextValidator.ensure_tenant_context(tenant)

    _ = access
    definition = PACK_DEFINITIONS_BY_CODE.get(scenario_code)
    if definition is None:
        raise _pack_not_found(
            code="PACK_SCENARIO_NOT_SUPPORTED", message="Scenario is not supported"
        )

    try:
        pack = await ensure_pack_by_code(session, tenant_slug=tenant.slug, pack_code=scenario_code)
    except ValueError:
        raise _pack_not_found(
            code="PACK_SCENARIO_NOT_SUPPORTED", message="Scenario is not supported"
        )

    if payload.name:
        pack.name = payload.name
    if payload.description is not None:
        pack.description = payload.description
    pack.is_active = payload.is_active
    await session.commit()
    await session.refresh(pack)
    return _pack_to_list_item(pack)


@router.get("", response_model=PackListResponse)
async def list_packs(
    tenant: TenantDep,
    session: SessionDep,
    access: PackReadAccess,
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE),
    sort: str | None = Query(None),
    filter: str | None = Query(None),
) -> PackListResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    pq = PageQuery(page=page, per_page=per_page)
    _ = access
    sq = SortQuery(raw=sort)
    fq = FilterQuery(raw=filter)

    tenant_scope = _tenant_scope_values(tenant)
    conditions = [
        DocumentPack.tenant_id.in_(tenant_scope),
        DocumentPack.deleted_at.is_(None),
    ]

    for flt in fq.parse():
        name = flt.field.lower()
        if name == "is_active":
            value = flt.value.strip().lower()
            if value in {"true", "1", "yes", "on"}:
                conditions.append(DocumentPack.is_active.is_(True))
            elif value in {"false", "0", "no", "off"}:
                conditions.append(DocumentPack.is_active.is_(False))
        elif name == "name" and flt.value:
            pattern = f"%{flt.value.strip()}%"
            conditions.append(DocumentPack.name.ilike(pattern))
        elif name == "code" and flt.value:
            conditions.append(DocumentPack.code == flt.value.strip())

    count_stmt = select(func.count()).select_from(DocumentPack).where(*conditions)
    total = int((await session.execute(count_stmt)).scalar_one())

    ordering: list[Any] = []
    for sort_item in sq.parse():
        column = None
        field = sort_item.field.lower()
        if field == "name":
            column = DocumentPack.name
        elif field == "code":
            column = DocumentPack.code
        elif field == "updated_at":
            column = DocumentPack.updated_at
        elif field in {"created_at", "createdat"}:
            column = DocumentPack.created_at
        if column is None:
            continue
        ordering.append(column.desc() if sort_item.direction < 0 else column.asc())
    if not ordering:
        ordering.append(DocumentPack.created_at.desc())

    stmt = (
        select(DocumentPack)
        .options(selectinload(DocumentPack.items))
        .where(*conditions)
        .order_by(*ordering)
        .offset(pq.offset)
        .limit(pq.per_page)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [_pack_to_list_item(pack).model_dump(mode="json") for pack in rows]
    payload = list_response(items, pagination_meta(pq.page, pq.per_page, total))
    return PackListResponse.model_validate(payload)


@router.post("/generate", response_model=TaskAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_pack_documents(
    payload: PackGenerateRequest,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: PackWriteAccess,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TaskAcceptedResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    _validate_pack_output_selection(payload.include_docx, payload.include_pdf)

    normalized_key = normalize_idempotency_key(idempotency_key)
    idem_state = getattr(request.state, "idempotency", {})
    request_hash = idem_state.get("fingerprint")
    if request_hash is None:
        request_hash = compute_request_hash(payload)
        idem_state = {"key": normalized_key, "fingerprint": request_hash}
        request.state.idempotency = idem_state
    idempotency = IdempotencyService(
        session=session,
        tenant_id=str(tenant.id),
        endpoint="packs.generate",
    )
    record, created_record = await idempotency.acquire(
        key=normalized_key,
        request_hash=request_hash,
        method=request.method.upper(),
        path=request.url.path,
    )
    if not created_record:
        return await idempotency.respond_from_store(
            record, model=TaskAcceptedResponse, response=response
        )

    try:
        company = await _get_company(session, tenant, payload.company_id, access=access)
        await _get_site(
            session, tenant, company, payload.site_id
        )  # validate: raises 404 if invalid
        persons = await _get_persons(session, tenant, company, payload.person_ids)
        await _enforce_person_invariants(session, tenant, persons)
        await _get_pack(session, tenant, payload.pack_code)

        task_id = str(uuid.uuid4())
        status_url = f"/api/v1/tasks/pipeline-runs/{task_id}"
        correlation_id = get_trace_id()
        result = TaskAcceptedResponse(
            task_id=task_id,
            correlation_id=correlation_id,
            status_url=status_url,
        )

        await idempotency.store_success(
            record,
            status_code=status.HTTP_202_ACCEPTED,
            body=result.model_dump(mode="json"),
        )
        await session.commit()
    except HTTPException as exc:
        await idempotency.store_failure(
            record,
            status_code=exc.status_code,
            detail={"detail": exc.detail},
        )
        await session.commit()
        raise
    except Exception as exc:
        await idempotency.store_failure(
            record,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc)},
        )
        await session.commit()
        raise

    try:
        task_payload = payload.model_dump(mode="json")
        generate_pack_task.apply_async(
            kwargs={
                "tenant_slug": tenant.slug,
                "tenant_id": str(tenant.id) if tenant.id else None,
                "payload": task_payload,
            },
            task_id=task_id,
            headers={"trace_id": correlation_id, "tenant": tenant.slug},
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        stored = await idempotency.get(key=normalized_key)
        if stored is not None:
            await idempotency.store_failure(
                stored,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": str(exc)},
            )
            await session.commit()
        logger.exception("packs.generate.enqueue_failed", exc_info=exc)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=api_problem_detail(
                code="INTERNAL_ERROR",
                message="Failed to queue pack generation task",
                error_type="server",
            ),
        ) from exc

    response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.post("/run", response_model=PackRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_pack(
    payload: PackRunRequest,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: PackWriteAccess,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PackRunResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    normalized_key = normalize_idempotency_key(idempotency_key)
    idem_state = getattr(request.state, "idempotency", {})
    request_hash = idem_state.get("fingerprint")
    if request_hash is None:
        request_hash = compute_request_hash(payload)
        idem_state = {"key": normalized_key, "fingerprint": request_hash}
        request.state.idempotency = idem_state
    idempotency = IdempotencyService(
        session=session,
        tenant_id=str(tenant.id),
        endpoint="packs.run",
    )
    existing_record = await idempotency.get(key=normalized_key)

    if existing_record is None and _has_single_task_limit(tenant):
        active_stmt = (
            select(func.count())
            .select_from(PipelineRun)
            .where(
                PipelineRun.tenant_id == tenant.id,
                PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
            )
        )
        active_runs = (await session.execute(active_stmt)).scalar_one()
        if active_runs:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=api_problem_detail(
                    code="TOO_MANY_REQUESTS",
                    message="A generation task is already running for this tenant",
                    error_type="packs",
                ),
                headers={"Retry-After": "30"},
            )

    record, created_record = await idempotency.acquire(
        key=normalized_key,
        request_hash=request_hash,
        method=request.method.upper(),
        path=request.url.path,
    )
    if not created_record:
        return await idempotency.respond_from_store(
            record, model=PackRunResponse, response=response
        )

    try:
        company = await _get_company(session, tenant, payload.company_id, access=access)
        site = await _get_site(session, tenant, company, payload.site_id)
        persons = await _get_persons(session, tenant, company, payload.person_ids)
        await _enforce_person_invariants(session, tenant, persons)

        pack = await _get_pack(session, tenant, payload.pack_code)
        service = PipelineService()

        batch_id = str(uuid.uuid4())
        tasks: list[PackRunTask] = []
        targets: list[Person | None] = persons or [None]

        for person in targets:
            context = _build_context(
                pack=pack,
                company=company,
                site=site,
                person=person,
                payload=payload,
            )
            context["letterhead"] = (
                payload.letterhead.model_dump(mode="json") if payload.letterhead else None
            )
            context["site_id"] = site.id if site else None
            for item in pack.items:
                template = item.template
                if template is None:
                    raise _pack_conflict(
                        "Pack item is missing a template", code="PACK_ITEM_NO_TEMPLATE"
                    )
                if item.template_version_id is None:
                    raise _pack_conflict(
                        "Pack item requires template_version_id",
                        code="PACK_ITEM_TEMPLATE_VERSION_REQUIRED",
                    )
                version = item.template_version
                if version is None:
                    version = await session.get(TemplateVersion, item.template_version_id)
                if version is None:
                    raise _pack_conflict(
                        "Pack item references missing template version",
                        code="PACK_ITEM_TEMPLATE_VERSION_MISSING",
                    )
                if str(version.tenant_id) != str(pack.tenant_id):
                    raise _pack_conflict(
                        "Pack item template version tenant mismatch",
                        code="PACK_ITEM_TEMPLATE_VERSION_TENANT_MISMATCH",
                    )
                if version.template_id != template.id:
                    raise _pack_conflict(
                        "Pack item template version mismatch",
                        code="PACK_ITEM_TEMPLATE_VERSION_MISMATCH",
                    )
                person_id = person.id if person is not None else None
                run_key = build_idempotency_key(
                    pack=pack,
                    template=template,
                    company_id=company.id,
                    site_id=site.id if site else None,
                    person_id=person_id,
                )
                run, _created = await service.ensure_pending_run(
                    session,
                    template=template,
                    template_version=version,
                    context=context,
                    replacements=None,
                    header_text=None,
                    footer_text=None,
                    idempotency_key=run_key,
                    output_basename=None,
                    tenant_id=template.tenant_id,
                )
                await session.flush()
                status_value = (
                    run.status.value
                    if isinstance(run.status, PipelineRunStatus)
                    else str(run.status)
                )
                task_identifier: str | None = None
                if run.status == PipelineRunStatus.QUEUED:
                    try:
                        trace_id = get_trace_id()
                        result = generate_document_task.apply_async(
                            args=[run.id],
                            kwargs={"tenant_slug": tenant.slug},
                            task_id=run.id,
                            headers={"trace_id": trace_id},
                        )
                        task_identifier = getattr(result, "id", None)
                    except Exception as exc:  # pragma: no cover - exercised in integration tests
                        logger.warning(
                            "generate_document_task.enqueue_failed",
                            extra={"run_id": run.id, "template_id": template.id},
                            exc_info=exc,
                        )
                        run = await service.run(
                            session=session,
                            template=template,
                            template_version=version,
                            context=context,
                            replacements=None,
                            header_text=None,
                            footer_text=None,
                            idempotency_key=run_key,
                            output_basename=None,
                            tenant_id=template.tenant_id,
                        )
                        status_value = (
                            run.status.value
                            if isinstance(run.status, PipelineRunStatus)
                            else str(run.status)
                        )
                tasks.append(
                    PackRunTask(
                        run_id=run.id,
                        template_id=template.id,
                        template_name=template.name,
                        person_id=person_id,
                        task_id=task_identifier,
                        status=status_value,
                    )
                )

        result = PackRunResponse(batch_id=batch_id, tasks=tasks)
        await idempotency.store_success(
            record,
            status_code=status.HTTP_202_ACCEPTED,
            body=result.model_dump(mode="json"),
        )
        await session.commit()
    except HTTPException as exc:
        await idempotency.store_failure(
            record,
            status_code=exc.status_code,
            detail={"detail": exc.detail},
        )
        await session.commit()
        raise
    except Exception as exc:
        await idempotency.store_failure(
            record,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc)},
        )
        await session.commit()
        raise

    response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("/download", summary="Download generated package archive")
async def download_pack_archive(
    tenant: TenantDep,
    access: PackReadAccess,
    request: Request,
    session: AsyncSession = Depends(get_session),
    storage_key: str = Query(
        ...,
        min_length=1,
        description="Object storage key of the generated ZIP archive",
    ),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    normalized_key = storage_key.strip()
    if not normalized_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=api_problem_detail(
                code="INVALID_STORAGE_KEY",
                message="storage_key must not be empty",
                error_type="packs",
            ),
        )
    tenant_prefix = f"{tenant_prefix_path(tenant.slug)}/"
    if not normalized_key.startswith(tenant_prefix):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="FORBIDDEN_STORAGE_KEY",
                message="storage_key does not belong to tenant",
                error_type="packs",
            ),
        )
    settings = get_settings()
    if settings.s3_backend == "minio":
        url = s3.generate_presigned_get_url(normalized_key)
        if url:
            logger.info(
                "packs.download.redirect",
                extra={"tenant": tenant.slug, "storage_key": normalized_key},
            )
            return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    storage = FileStorageService.default()
    payload: bytes | None = None
    try:
        if storage.has(normalized_key):
            payload = storage.get(normalized_key)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=api_problem_detail(
                code="MALFORMED_STORAGE_KEY",
                message="storage_key is malformed",
                error_type="packs",
            ),
        ) from exc

    if payload is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PACK_ARCHIVE_NOT_FOUND",
                message="Archive not found",
                error_type="packs",
            ),
        )
    filename = normalized_key.rsplit("/", 1)[-1] or "package.zip"
    logger.info(
        "packs.download.stream",
        extra={"tenant": tenant.slug, "storage_key": normalized_key, "bytes": len(payload)},
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="download",
        object_type="pack_archive",
        object_id=normalized_key,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"bytes": len(payload)},
    )
    await session.commit()
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-cache",
        "Content-Length": str(len(payload)),
    }
    return StreamingResponse(BytesIO(payload), media_type="application/zip", headers=headers)


@router.get("/{pack_id}/download-archive", summary="Download ZIP with pack files")
async def download_pack_files_archive(
    pack_id: str,
    request: Request,
    tenant: TenantDep,
    access: PackReadAccess,
    session: SessionDep,
) -> StreamingResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    files_stmt = select(StoredFile).where(
        StoredFile.tenant_id == tenant.id,
        StoredFile.pack_id == pack_id,
        StoredFile.scan_status == FileScanStatus.CLEAN,
    )
    files = list((await session.scalars(files_stmt)).all())
    if not files:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PACK_ARCHIVE_NOT_FOUND",
                message="No clean files for this pack",
                error_type="packs",
            ),
        )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            try:
                with s3.stream_object(key=file.storage_key) as stream:
                    content = stream.read()
            except s3.S3OperationError as exc:
                status_code, detail = exc.as_http_detail()
                raise HTTPException(status_code, detail=detail) from exc

            arcname = file.original_name or (file.storage_key.rsplit("/", 1)[-1] or file.id)
            archive.writestr(arcname, content)

    payload = buffer.getvalue()
    headers = {
        "Content-Disposition": f'attachment; filename="pack-{pack_id}.zip"',
        "Content-Length": str(len(payload)),
        "Cache-Control": "no-cache",
    }

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="download",
        object_type="pack_archive",
        object_id=pack_id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"file_count": len(files)},
    )
    await session.commit()

    return StreamingResponse(BytesIO(payload), media_type="application/zip", headers=headers)


@router.get("/{pack_run_id}/safety-summary")
async def pack_safety_summary(
    pack_run_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: PackReadAccess,
) -> dict[str, list[dict[str, object]]]:
    """Return safety summary for pack run consumers (risk+PPE completeness)."""

    TenantContextValidator.ensure_tenant_context(tenant)

    del access
    tenant_scope = _tenant_scope_values(tenant)

    people_stmt = (
        select(Person)
        .where(Person.tenant_id.in_(tenant_scope), Person.deleted_at.is_(None))
        .limit(100)
    )
    persons = (await session.execute(people_stmt)).scalars().all()

    output: list[dict[str, object]] = []
    for person in persons:
        risk_map_stmt = (
            select(SafetyRiskMap)
            .where(
                SafetyRiskMap.tenant_id.in_(tenant_scope),
                SafetyRiskMap.entity_type == "person",
                SafetyRiskMap.entity_id == person.id,
                SafetyRiskMap.status == "active",
                SafetyRiskMap.deleted_at.is_(None),
            )
            .order_by(SafetyRiskMap.updated_at.desc())
            .limit(1)
        )
        active_risk_map = (await session.execute(risk_map_stmt)).scalar_one_or_none()

        levels: list[str] = []
        if active_risk_map is not None:
            level_stmt = select(RiskMapItem.risk_level).where(
                RiskMapItem.tenant_id.in_(tenant_scope),
                RiskMapItem.risk_map_id == active_risk_map.id,
                RiskMapItem.deleted_at.is_(None),
                RiskMapItem.risk_level.is_not(None),
            )
            raw_levels = [
                str(level) for level in (await session.execute(level_stmt)).scalars().all()
            ]
            rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            levels = sorted(set(raw_levels), key=lambda value: rank.get(value, -1))

        # PPE personal-card lookup removed in СИЗ Срез-1: family-B tables
        # (ppe_personal_cards/...) never had a write path — this always resolved
        # to an empty list. Real personal cards now live at /ppe/employees/{id}/card.
        issued_ppe: list[dict[str, object]] = []

        missing_ppe: dict[str, float] = {}
        has_clearance = PackSafetySummaryService.has_clearance(
            risk_levels=levels, missing_ppe=missing_ppe
        )

        output.append(
            {
                "person_id": person.id,
                "fio": " ".join(
                    filter(None, [person.last_name, person.first_name, person.middle_name])
                ),
                "position": getattr(person.position, "name", None),
                "site": getattr(getattr(person.workplace, "site", None), "name", None),
                "active_risk_map_id": active_risk_map.id if active_risk_map else None,
                "risk_levels": levels,
                "required_ppe": [],
                "issued_ppe": issued_ppe,
                "missing_ppe": [
                    {"ppe_catalog_id": catalog_id, "quantity": quantity}
                    for catalog_id, quantity in missing_ppe.items()
                ],
                "has_clearance": has_clearance,
            }
        )

    return {"pack_run_id": pack_run_id, "persons": output}
