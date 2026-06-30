"""Risk endpoints — methodology / hazard / control / matrix / map config (ARCH-4 slice 6)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select

from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.api.routes.risk._common import (
    AdminAccess,
    ControlIn,
    EditorAccess,
    HazardIn,
    MatrixUp,
    MethodologyIn,
    MethodologyOut,
    MethodologyUpdate,
    RiskMapIn,
    RiskMapOut,
    SessionDep,
    TenantDep,
    _get_tenant_entity,
    _slugify_code,
    engine_router,
)
from app.domains.risk import rebuild_matrix_from_methodology, recalc_risk_map
from app.models.models import (
    Company,
    DocumentPack,
    Position,
    RiskMap,
    RiskMethodology,
    Site,
)
from app.models.risk import (
    RiskControl,
    RiskHazard,
    RiskMatrixCell,
)


@engine_router.post("/methodologies", response_model=MethodologyOut)
async def create_methodology(
    payload: MethodologyIn,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    code = _slugify_code(payload.code or payload.name)
    existing = (
        await session.execute(
            select(RiskMethodology).where(
                RiskMethodology.tenant_id == tenant_id,
                (RiskMethodology.name == payload.name) | (RiskMethodology.code == code),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Methodology name already exists")

    definition = {
        "severity_scale": [item.model_dump() for item in payload.severity_scale],
        "likelihood_scale": [item.model_dump() for item in payload.likelihood_scale],
        "bands": [band.model_dump() for band in payload.bands],
    }
    record = RiskMethodology(
        tenant_id=tenant_id,
        code=code,
        name=payload.name,
        definition=definition,
    )
    session.add(record)
    await session.flush()
    await session.commit()
    return MethodologyOut(
        id=record.id,
        code=record.code,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
        version=record.version,
    )


@engine_router.get("/methodologies", response_model=list[MethodologyOut])
async def list_methodologies(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> list[MethodologyOut] | Response:
    tenant_id = str(tenant.id)
    records = list(
        (
            await session.execute(
                select(RiskMethodology).where(RiskMethodology.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[("total", len(records)), ("kind", "methodologies")],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    result: list[MethodologyOut] = []
    for record in records:
        definition = record.definition or {}
        result.append(
            MethodologyOut(
                id=record.id,
                code=record.code,
                name=record.name,
                severity_scale=definition.get("severity_scale", []),
                likelihood_scale=definition.get("likelihood_scale", []),
                bands=definition.get("bands", []),
                version=record.version,
            )
        )
    return result


@engine_router.get("/methodologies/{methodology_id}", response_model=MethodologyOut)
async def get_methodology(
    methodology_id: str, session: SessionDep, tenant: TenantDep, _: EditorAccess
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(session, RiskMethodology, tenant_id, methodology_id)
    definition = record.definition or {}
    return MethodologyOut(
        id=record.id,
        code=record.code,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
        version=record.version,
    )


@engine_router.put("/methodologies/{methodology_id}", response_model=MethodologyOut)
async def update_methodology(
    methodology_id: str,
    payload: MethodologyUpdate,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(session, RiskMethodology, tenant_id, methodology_id)

    if payload.name and payload.name != record.name:
        duplicate = (
            await session.execute(
                select(RiskMethodology).where(
                    RiskMethodology.tenant_id == tenant_id,
                    RiskMethodology.name == payload.name,
                    RiskMethodology.id != record.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status.HTTP_409_CONFLICT, "Methodology name already exists")
        record.name = payload.name

    if payload.code and payload.code != record.code:
        code = _slugify_code(payload.code)
        duplicate_code = (
            await session.execute(
                select(RiskMethodology).where(
                    RiskMethodology.tenant_id == tenant_id,
                    RiskMethodology.code == code,
                    RiskMethodology.id != record.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate_code:
            raise HTTPException(status.HTTP_409_CONFLICT, "Methodology code already exists")
        record.code = code

    definition = record.definition or {}
    if payload.severity_scale is not None:
        definition["severity_scale"] = [item.model_dump() for item in payload.severity_scale]
    if payload.likelihood_scale is not None:
        definition["likelihood_scale"] = [item.model_dump() for item in payload.likelihood_scale]
    if payload.bands is not None:
        definition["bands"] = [band.model_dump() for band in payload.bands]
    record.definition = definition

    await session.flush()
    await session.commit()
    return MethodologyOut(
        id=record.id,
        code=record.code,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
        version=record.version,
    )


@engine_router.delete(
    "/methodologies/{methodology_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_methodology(
    methodology_id: str, session: SessionDep, tenant: TenantDep, _: AdminAccess
) -> None:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(session, RiskMethodology, tenant_id, methodology_id)
    await session.delete(record)
    await session.commit()
    return {"ok": True}


@engine_router.post("/hazards", status_code=status.HTTP_200_OK)
async def add_hazard(
    payload: HazardIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> dict[str, str]:
    tenant_id = str(tenant.id)
    existing = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_id,
                RiskHazard.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Hazard code already exists")

    hazard = RiskHazard(
        tenant_id=tenant_id,
        code=payload.code,
        title=payload.title,
        module=payload.module,
        description=payload.description,
        recommended_measures=[
            measure.model_dump(mode="json") for measure in payload.recommended_measures
        ],
    )
    session.add(hazard)
    await session.flush()
    await session.commit()
    return {"id": hazard.id}


@engine_router.post("/controls", status_code=status.HTTP_200_OK)
async def add_control(
    payload: ControlIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> dict[str, str]:
    tenant_id = str(tenant.id)
    existing = (
        await session.execute(
            select(RiskControl).where(
                RiskControl.tenant_id == tenant_id,
                RiskControl.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Control code already exists")

    control = RiskControl(
        tenant_id=tenant_id,
        code=payload.code,
        title=payload.title,
        type=payload.type,
        description=payload.description,
    )
    session.add(control)
    await session.flush()
    await session.commit()
    return {"id": control.id}


@engine_router.put("/matrix", status_code=status.HTTP_200_OK)
async def set_matrix(
    payload: MatrixUp,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> dict[str, int | bool]:
    tenant_id = str(tenant.id)
    cells: list[RiskMatrixCell]
    if payload.methodology_id and not payload.rows:
        methodology = await _get_tenant_entity(
            session, RiskMethodology, tenant_id, payload.methodology_id
        )
        cells = await rebuild_matrix_from_methodology(session, tenant_id, methodology)
    else:
        await session.execute(delete(RiskMatrixCell).where(RiskMatrixCell.tenant_id == tenant_id))
        cells = [
            RiskMatrixCell(
                tenant_id=tenant_id,
                severity=row.severity,
                likelihood=row.likelihood,
                score=row.score,
                band=row.band,
            )
            for row in payload.rows
        ]
        session.add_all(cells)
    await session.commit()
    return {"ok": True, "count": len(cells)}


@engine_router.post("/maps", response_model=RiskMapOut)
async def save_risk_map(
    payload: RiskMapIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> RiskMapOut:
    tenant_id = str(tenant.id)
    methodology = await _get_tenant_entity(
        session, RiskMethodology, tenant_id, payload.methodology_id
    )
    await _get_tenant_entity(session, Company, tenant_id, payload.company_id)
    if payload.site_id:
        await _get_tenant_entity(session, Site, tenant_id, payload.site_id)
    if payload.position_id:
        await _get_tenant_entity(session, Position, tenant_id, payload.position_id)
    if payload.document_pack_id:
        await _get_tenant_entity(session, DocumentPack, tenant_id, payload.document_pack_id)

    matrix = await recalc_risk_map(
        session,
        tenant_id,
        methodology,
        company_id=payload.company_id,
        site_id=payload.site_id,
        position_id=payload.position_id,
        document_pack_id=payload.document_pack_id,
    )

    existing = (
        await session.execute(
            select(RiskMap).where(
                RiskMap.tenant_id == tenant_id,
                RiskMap.company_id == payload.company_id,
                RiskMap.site_id == payload.site_id,
                RiskMap.position_id == payload.position_id,
                RiskMap.methodology_id == payload.methodology_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.matrix = matrix
        existing.recalculated_at = datetime.now(timezone.utc)
        target = existing
    else:
        target = RiskMap(
            tenant_id=tenant_id,
            methodology_id=payload.methodology_id,
            company_id=payload.company_id,
            site_id=payload.site_id,
            position_id=payload.position_id,
            document_pack_id=payload.document_pack_id,
            matrix=matrix,
            recalculated_at=datetime.now(timezone.utc),
        )
        session.add(target)

    await session.commit()
    return RiskMapOut(
        id=target.id,
        matrix=matrix,
        methodology_id=payload.methodology_id,
        company_id=payload.company_id,
        site_id=payload.site_id,
        position_id=payload.position_id,
        document_pack_id=payload.document_pack_id,
    )


@engine_router.get("/maps", response_model=list[RiskMapOut])
async def list_risk_maps(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    company_id: str = Query(..., alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    methodology_id: str | None = Query(default=None, alias="methodology_id"),
) -> list[RiskMapOut] | Response:
    tenant_id = str(tenant.id)
    await _get_tenant_entity(session, Company, tenant_id, company_id)
    stmt = select(RiskMap).where(RiskMap.tenant_id == tenant_id, RiskMap.company_id == company_id)
    if site_id:
        stmt = stmt.where(RiskMap.site_id == site_id)
    if position_id:
        stmt = stmt.where(RiskMap.position_id == position_id)
    if methodology_id:
        stmt = stmt.where(RiskMap.methodology_id == methodology_id)

    records = list((await session.execute(stmt)).scalars().all())
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[
            ("total", len(records)),
            ("kind", "maps"),
            ("company", company_id),
            ("site", site_id or ""),
            ("position", position_id or ""),
            ("methodology", methodology_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return [
        RiskMapOut(
            id=record.id,
            matrix=record.matrix,
            methodology_id=record.methodology_id,
            company_id=record.company_id,
            site_id=record.site_id,
            position_id=record.position_id,
            document_pack_id=record.document_pack_id,
        )
        for record in records
    ]
