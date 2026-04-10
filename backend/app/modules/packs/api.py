from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.models.models import (
    PackagePresetItem,
    PackRun,
    PackRunItem,
    PackRunLog,
    TemplateVersion,
    Tenant,
)
from app.modules.packs.schemas import (
    DownloadRead,
    MappingPreviewRequest,
    PackagePresetCreate,
    PackagePresetItemCreate,
    PackagePresetItemPatch,
    PackagePresetItemRead,
    PackagePresetPatch,
    PackagePresetRead,
    PackageProfileCreate,
    PackageProfilePatch,
    PackageProfileRead,
    PackRunAccepted,
    PackRunCreate,
    PackRunItemRead,
    PackRunLogRead,
    PackRunRead,
    SourcePreviewRead,
)
from app.modules.packs.service import (
    MappingValidationService,
    NamingRuleEngine,
    PackageService,
    PackRunService,
    load_source_rows,
)

router = APIRouter(tags=["packs-v2"])

_PACKS_V2_TYPE = "packs"


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(code=code, message=message, error_type=_PACKS_V2_TYPE),
    )


def _bad_request(code: str, message: str, *, field: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(code=code, message=message, error_type=_PACKS_V2_TYPE, field=field),
    )


def _profile_read(model) -> PackageProfileRead:
    return PackageProfileRead(
        id=model.id,
        code=model.code,
        name=model.name,
        description=model.description,
        pipeline_steps_json=model.pipeline_steps_json or [],
        concurrency_limit=model.concurrency_limit,
        status=model.status.value if hasattr(model.status, "value") else str(model.status),
    )


def _item_read(model) -> PackagePresetItemRead:
    return PackagePresetItemRead(
        id=model.id,
        order_no=model.order_no,
        template_id=model.template_id,
        template_version_id=model.template_version_id,
        replace_mode=model.replace_mode.value if hasattr(model.replace_mode, "value") else str(model.replace_mode),
        output_format=model.output_format.value if hasattr(model.output_format, "value") else str(model.output_format),
        is_required=model.is_required,
    )


async def _preset_read(session: AsyncSession, model) -> PackagePresetRead:
    items = (
        await session.execute(
            select(PackagePresetItem)
            .where(PackagePresetItem.package_preset_id == model.id, PackagePresetItem.deleted_at.is_(None))
            .order_by(PackagePresetItem.order_no.asc())
        )
    ).scalars().all()
    return PackagePresetRead(
        id=model.id,
        code=model.code,
        name=model.name,
        description=model.description,
        package_profile_id=model.package_profile_id,
        naming_rule=model.naming_rule,
        source_type=model.source_type.value if hasattr(model.source_type, "value") else str(model.source_type),
        mapping_json=model.mapping_json or {},
        options_json=model.options_json or {},
        status=model.status.value if hasattr(model.status, "value") else str(model.status),
        items=[_item_read(i) for i in items],
    )


@router.post("/package-profiles", response_model=PackageProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: PackageProfileCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackageProfileRead:
    model = await PackageService(session).create_profile(tenant_id=str(tenant.id), payload=payload.model_dump())
    await session.commit()
    return _profile_read(model)


@router.get("/package-profiles", response_model=list[PackageProfileRead])
async def list_profiles(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PackageProfileRead]:
    rows = await PackageService(session).list_profiles(tenant_id=str(tenant.id))
    return [_profile_read(row) for row in rows]


@router.get("/package-profiles/{profile_id}", response_model=PackageProfileRead)
async def get_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackageProfileRead:
    model = await PackageService(session).get_profile(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise _not_found("PACKAGE_PROFILE_NOT_FOUND", "Profile not found")
    return _profile_read(model)


@router.patch("/package-profiles/{profile_id}", response_model=PackageProfileRead)
async def patch_profile(profile_id: str, payload: PackageProfilePatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackageProfileRead:
    model = await PackageService(session).get_profile(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise _not_found("PACKAGE_PROFILE_NOT_FOUND", "Profile not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(model, key, value)
    await session.commit()
    return _profile_read(model)


@router.delete("/package-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> Response:
    model = await PackageService(session).get_profile(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise _not_found("PACKAGE_PROFILE_NOT_FOUND", "Profile not found")
    from datetime import datetime, timezone

    model.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/package-presets", response_model=PackagePresetRead, status_code=status.HTTP_201_CREATED)
async def create_preset(payload: PackagePresetCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackagePresetRead:
    service = PackageService(session)
    model = await service.create_preset(tenant_id=str(tenant.id), payload=payload.model_dump())
    await session.commit()
    return await _preset_read(session, model)


@router.get("/package-presets", response_model=list[PackagePresetRead])
async def list_presets(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PackagePresetRead]:
    service = PackageService(session)
    rows = await service.list_presets(tenant_id=str(tenant.id))
    return [await _preset_read(session, row) for row in rows]


@router.get("/package-presets/{preset_id}", response_model=PackagePresetRead)
async def get_preset(preset_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackagePresetRead:
    service = PackageService(session)
    model = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if model is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    return await _preset_read(session, model)


@router.patch("/package-presets/{preset_id}", response_model=PackagePresetRead)
async def patch_preset(preset_id: str, payload: PackagePresetPatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackagePresetRead:
    service = PackageService(session)
    model = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if model is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(model, key, value)
    await session.commit()
    return await _preset_read(session, model)


@router.post("/package-presets/{preset_id}/items", response_model=PackagePresetItemRead, status_code=status.HTTP_201_CREATED)
async def create_preset_item(preset_id: str, payload: PackagePresetItemCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackagePresetItemRead:
    service = PackageService(session)
    preset = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if preset is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    item = await service.add_item(str(tenant.id), preset, payload)
    await session.commit()
    return _item_read(item)


@router.patch("/package-presets/{preset_id}/items/{item_id}", response_model=PackagePresetItemRead)
async def patch_preset_item(
    preset_id: str,
    item_id: str,
    payload: PackagePresetItemPatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> PackagePresetItemRead:
    service = PackageService(session)
    item = await service.get_item(str(tenant.id), preset_id, item_id)
    if item is None:
        raise _not_found("PACKAGE_PRESET_ITEM_NOT_FOUND", "Preset item not found")
    data = payload.model_dump(exclude_unset=True)
    if "replace_mode" in data and data["replace_mode"] == "dry-run":
        data["replace_mode"] = "preview"
    for key, value in data.items():
        setattr(item, key, value)
    await session.commit()
    return _item_read(item)


@router.delete("/package-presets/{preset_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset_item(
    preset_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> Response:
    from datetime import datetime, timezone

    service = PackageService(session)
    item = await service.get_item(str(tenant.id), preset_id, item_id)
    if item is None:
        raise _not_found("PACKAGE_PRESET_ITEM_NOT_FOUND", "Preset item not found")
    item.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/package-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(preset_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> Response:
    from datetime import datetime, timezone

    service = PackageService(session)
    preset = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if preset is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    preset.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/package-presets/{preset_id}:validate")
async def validate_preset(preset_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict[str, Any]:
    service = PackageService(session)
    preset = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if preset is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    items = (
        await session.execute(select(PackagePresetItem).where(PackagePresetItem.package_preset_id == preset.id))
    ).scalars().all()
    errors: list[str] = []
    warnings: list[str] = []
    for item in items:
        tv = await session.get(TemplateVersion, item.template_version_id)
        if tv is None or tv.deleted_at is not None:
            errors.append(f"template_version_id={item.template_version_id} is not available")
        elif str(tv.tenant_id) != str(preset.tenant_id):
            errors.append(f"template_version_id={item.template_version_id} tenant mismatch for preset")
    warnings.extend(NamingRuleEngine().validate_rule(preset.naming_rule))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "items_count": len(items)}


@router.post("/package-presets/{preset_id}:upload-source", response_model=SourcePreviewRead)
async def upload_source_preview(preset_id: str, payload: MappingPreviewRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> SourcePreviewRead:
    service = PackageService(session)
    preset = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if preset is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    source_type, columns, rows = await load_source_rows(
        session, payload.source_file_id, payload.rows, tenant_id=str(tenant.id)
    )
    return SourcePreviewRead(source_file_id=payload.source_file_id, source_type=source_type, columns=columns, rows_count=len(rows), sample_rows=rows[:5])


@router.post("/package-presets/{preset_id}:preview-mapping")
async def preview_mapping(preset_id: str, payload: MappingPreviewRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict[str, Any]:
    service = PackageService(session)
    preset = await service.get_preset(tenant_id=str(tenant.id), preset_id=preset_id)
    if preset is None:
        raise _not_found("PACKAGE_PRESET_NOT_FOUND", "Preset not found")
    source_type, columns, rows = await load_source_rows(
        session, payload.source_file_id, payload.rows, tenant_id=str(tenant.id)
    )
    validator = MappingValidationService()
    validator.validate(preset.mapping_json or {}, columns)
    mapped = [validator.apply(preset.mapping_json or {}, row) for row in rows[: payload.row_limit]]
    return {"source_type": source_type, "preview": mapped}


@router.post("/pack-runs", response_model=PackRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_pack_run(
    payload: PackRunCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_tenant: str | None = Header(default=None, alias="X-Tenant"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> PackRunAccepted:
    if not x_tenant:
        raise _bad_request("X_TENANT_REQUIRED", "X-Tenant header is required", field="X-Tenant")
    if not idempotency_key:
        raise _bad_request("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required", field="Idempotency-Key")

    _, _, rows = await load_source_rows(session, payload.source_file_id, payload.rows, tenant_id=str(tenant.id))
    run = await PackRunService(session).create_run(
        tenant_id=str(tenant.id),
        payload=payload,
        idempotency_key=idempotency_key,
        rows=rows,
    )
    await session.commit()
    return PackRunAccepted(pack_run_id=run.id, status=run.status.value if hasattr(run.status, "value") else str(run.status))


@router.get("/pack-runs", response_model=list[PackRunRead])
async def list_runs(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PackRunRead]:
    rows = (
        await session.execute(select(PackRun).where(PackRun.tenant_id == str(tenant.id), PackRun.deleted_at.is_(None)).order_by(PackRun.created_at.desc()))
    ).scalars().all()
    return [
        PackRunRead(
            id=row.id,
            package_preset_id=row.package_preset_id,
            package_profile_id=row.package_profile_id,
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            source_rows_count=row.source_rows_count,
            selected_rows_count=row.selected_rows_count,
            stats_json=row.stats_json or {},
            created_at=row.created_at,
            started_at=row.started_at,
            ended_at=row.ended_at,
        )
        for row in rows
    ]


@router.get("/pack-runs/{run_id}", response_model=PackRunRead)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackRunRead:
    row = await session.get(PackRun, run_id)
    if row is None or row.tenant_id != str(tenant.id):
        raise _not_found("PACK_RUN_NOT_FOUND", "Pack run not found")
    return PackRunRead(
        id=row.id,
        package_preset_id=row.package_preset_id,
        package_profile_id=row.package_profile_id,
        status=row.status.value if hasattr(row.status, "value") else str(row.status),
        source_rows_count=row.source_rows_count,
        selected_rows_count=row.selected_rows_count,
        stats_json=row.stats_json or {},
        created_at=row.created_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


@router.get("/pack-runs/{run_id}/items", response_model=list[PackRunItemRead])
async def list_run_items(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PackRunItemRead]:
    rows = (
        await session.execute(select(PackRunItem).where(PackRunItem.pack_run_id == run_id, PackRunItem.tenant_id == str(tenant.id)).order_by(PackRunItem.row_no.asc()))
    ).scalars().all()
    return [PackRunItemRead(id=r.id, row_no=r.row_no, status=r.status.value if hasattr(r.status, "value") else str(r.status), file_name=r.filename, error_code=r.error_code) for r in rows]


@router.get("/pack-runs/{run_id}/timeline", response_model=list[PackRunLogRead])
async def get_timeline(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PackRunLogRead]:
    rows = (
        await session.execute(select(PackRunLog).where(PackRunLog.pack_run_id == run_id, PackRunLog.tenant_id == str(tenant.id)).order_by(PackRunLog.created_at.asc()))
    ).scalars().all()
    return [PackRunLogRead.model_validate(row) for row in rows]


@router.post("/pack-runs/{run_id}:cancel", response_model=PackRunRead)
async def cancel_run(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PackRunRead:
    row = await session.get(PackRun, run_id)
    if row is None or row.tenant_id != str(tenant.id):
        raise _not_found("PACK_RUN_NOT_FOUND", "Pack run not found")
    row.status = "canceled"
    await session.commit()
    return await get_run(run_id, session, tenant)


@router.post("/pack-runs/{run_id}:retry-failed", response_model=dict[str, int])
async def retry_failed(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict[str, int]:
    rows = (
        await session.execute(select(PackRunItem).where(PackRunItem.pack_run_id == run_id, PackRunItem.tenant_id == str(tenant.id), PackRunItem.status == "failed"))
    ).scalars().all()
    for row in rows:
        row.status = "queued"
        row.error_code = None
        row.error_payload = None
    await session.commit()
    return {"retried": len(rows)}


@router.get("/pack-runs/{run_id}/download", response_model=DownloadRead)
async def download_run(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> DownloadRead:
    row = await session.get(PackRun, run_id)
    if row is None or row.tenant_id != str(tenant.id):
        raise _not_found("PACK_RUN_NOT_FOUND", "Pack run not found")
    return DownloadRead(url=f"/api/v1/pack-runs/{run_id}/download.zip")
