"""Pack endpoints — scenarios, pack listing, document generation (ARCH-4 slice 8 split)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.routes.packs._common import (
    PackReadAccess,
    PackWriteAccess,
    SessionDep,
    TenantDep,
    _enforce_person_invariants,
    _get_company,
    _get_pack,
    _get_persons,
    _get_site,
    _pack_not_found,
    _pack_to_list_item,
    _serialize_definition,
    _tenant_scope_values,
    _validate_pack_output_selection,
    logger,
    router,
)
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
from app.core.tenant_validation import TenantContextValidator
from app.core.tracing import get_trace_id
from app.domains.packs.definitions import DEFAULT_PACKS, PACK_DEFINITIONS_BY_CODE
from app.domains.packs.seeder import ensure_pack_by_code
from app.models.models import (
    DocumentPack,
)
from app.schemas.pack import (
    PackFromScenarioRequest,
    PackGenerateRequest,
    PackListItem,
    PackListResponse,
    PackScenarioListResponse,
)
from app.schemas.task import TaskAcceptedResponse
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.tasks import generate_pack_task


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
