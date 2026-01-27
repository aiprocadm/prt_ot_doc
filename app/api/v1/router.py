from __future__ import annotations

import hashlib
import json
import logging
import sys
import types
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Mapping
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record, require_tenant_slug
from app.api.routes import (
    audit,
    auth,
    companies,
    documents,
    files,
    incidents,
    inspections,
    journals,
    npa,
    packs,
    persons,
    ppe,
    risk,
    sites,
    tasks,
    tenants,
    training,
)
from app.core.payload_constraints import (
    PayloadConstraintError,
    enforce_mapping_constraints,
    normalize_output_basename,
)
from app.core.security import AccessContext, abac
from app.core.tracing import get_trace_id
from app.domains.files.utils import build_dated_prefix
from app.models.document import Document
from app.models.models import (
    DocumentPackItem,
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.repository import (
    get_active_template_with_version,
    list_persons,
    list_templates,
)
from app.repository import (
    create_template as create_template_record,
)
from app.schemas.common import PipelineRunRead, TemplatePage
from app.schemas.person import PersonPage
from app.schemas.template import TemplateCreate, TemplateVersionMetadata
from app.services.docx import DocxService
from app.services.file_storage import FileStorageService
from app.services.pipeline import PipelineService
from app.services.tasks import run_pipeline_task

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ATTACHMENT_HEADER = 'attachment; filename="{filename}"'

UploadDocx = Annotated[UploadFile, File(media_type=DOCX_CONTENT_TYPE)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
_MANAGERIAL_ROLES = ["admin"]
_EDITOR_ROLES = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_MANAGERIAL_ROLES, action="read")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_EDITOR_ROLES, action="write")),
]

router = APIRouter()
tenant_router = APIRouter(dependencies=[Depends(require_tenant_slug)])

router.include_router(auth.router, prefix="/auth", tags=["auth"])
tenant_router.include_router(audit.router, prefix="/audit", tags=["audit"])
tenant_router.include_router(files.router, prefix="/files", tags=["files"])
tenant_router.include_router(packs.router, prefix="/packs", tags=["packs"])
tenant_router.include_router(incidents.router, tags=["incidents"])
tenant_router.include_router(inspections.router, tags=["inspections"])
tenant_router.include_router(npa.router, tags=["npa"])
tenant_router.include_router(ppe.router, tags=["ppe"])
tenant_router.include_router(journals.router, tags=["journals"])
tenant_router.include_router(risk.router, tags=["risks"])
tenant_router.include_router(sites.router, tags=["sites"])
tenant_router.include_router(documents.router, prefix="/documents", tags=["documents"])
tenant_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
tenant_router.include_router(tenants.router)
tenant_router.include_router(companies.router)
tenant_router.include_router(persons.router)
tenant_router.include_router(training.router, tags=["training"])

router.include_router(tenant_router)

setattr(router, "run_pipeline_task", run_pipeline_task)


class _TaskProxy(types.ModuleType):
    def __init__(self, name: str, task: object) -> None:
        super().__init__(name)
        super().__setattr__("_task", task)

    def __getattr__(self, item: str) -> object:
        return getattr(self._task, item)

    def __setattr__(self, key: str, value: object) -> None:
        if key == "_task":
            super().__setattr__(key, value)
            return
        setattr(self._task, key, value)


_TASK_MODULE_NAME = "app.api.v1.router.run_pipeline_task"
if _TASK_MODULE_NAME not in sys.modules:
    sys.modules[_TASK_MODULE_NAME] = _TaskProxy(_TASK_MODULE_NAME, run_pipeline_task)

logger = logging.getLogger(__name__)


class PipelineRunPayload(BaseModel):
    context: dict[str, Any]
    idempotency_key: str | None = None
    header_text: str | None = None
    footer_text: str | None = None
    replacements: dict[str, Any] | None = None
    output_basename: str | None = None

    model_config = ConfigDict(extra="forbid")


@dataclass
class PipelineRunRequestData:
    """Normalized payload for pipeline runs."""

    context: dict[str, Any]
    replacements: dict[str, str] | None
    header_text: str | None
    footer_text: str | None
    idempotency_key: str | None
    output_basename: str | None


MAX_TEMPLATE_SIZE_BYTES = 8 * 1024 * 1024
MAX_METADATA_JSON_BYTES = 64 * 1024


def _tenant_scope(tenant: Tenant) -> tuple[str, ...]:
    values = [tenant.slug]
    if getattr(tenant, "id", None):
        values.append(str(tenant.id))
    return tuple(values)


async def _template_version_in_use(
    session: AsyncSession,
    *,
    tenant: Tenant,
    template_version_id: str,
) -> bool:
    tenant_scope = _tenant_scope(tenant)
    document_count = await session.scalar(
        select(func.count()).select_from(Document).where(
            Document.template_version_id == template_version_id,
            Document.tenant_id.in_(tenant_scope),
        )
    )
    pipeline_count = await session.scalar(
        select(func.count()).select_from(PipelineRun).where(
            PipelineRun.template_version_id == template_version_id,
            PipelineRun.tenant_id.in_(tenant_scope),
        )
    )
    pack_count = await session.scalar(
        select(func.count()).select_from(DocumentPackItem).where(
            DocumentPackItem.template_version_id == template_version_id,
            DocumentPackItem.tenant_id.in_(tenant_scope),
        )
    )
    return any(
        count and count > 0 for count in (document_count, pipeline_count, pack_count)
    )


async def _template_in_use(
    session: AsyncSession,
    *,
    tenant: Tenant,
    template_id: str,
) -> bool:
    tenant_scope = _tenant_scope(tenant)
    document_count = await session.scalar(
        select(func.count()).select_from(Document).where(
            Document.template_id == template_id,
            Document.tenant_id.in_(tenant_scope),
        )
    )
    pipeline_count = await session.scalar(
        select(func.count()).select_from(PipelineRun).where(
            PipelineRun.template_id == template_id,
            PipelineRun.tenant_id.in_(tenant_scope),
        )
    )
    pack_count = await session.scalar(
        select(func.count()).select_from(DocumentPackItem).where(
            DocumentPackItem.template_id == template_id,
            DocumentPackItem.tenant_id.in_(tenant_scope),
        )
    )
    return any(
        count and count > 0 for count in (document_count, pipeline_count, pack_count)
    )


def _parse_json_object(value: str | None, *, field: str) -> dict[str, Any]:
    """Parse a JSON object from a string payload.

    FastAPI forms submit values as strings. Empty values are treated as missing
    objects. When a non-dict payload is received we return a 400 error that
    names the field explicitly to aid debugging on the client side.
    """

    if value is None:
        return {}

    trimmed = value.strip()
    if not trimmed:
        return {}

    try:
        data = json.loads(trimmed)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{field} must be a valid JSON object"
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} must be a JSON object")

    return data


def _parse_json_list(value: str | None, *, field: str) -> list[Any]:
    if value is None:
        return []
    trimmed = value.strip()
    if not trimmed:
        return []
    try:
        data = json.loads(trimmed)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{field} must be a valid JSON array"
        ) from exc
    if not isinstance(data, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} must be a JSON array")
    return data


def _enforce_mapping_constraints(mapping: Mapping[str, Any], *, field: str) -> None:
    try:
        enforce_mapping_constraints(mapping, field=field)
    except PayloadConstraintError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def _ensure_form_string(value: object, *, field: str) -> str:
    """Ensure multipart form values are decoded strings."""

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{field} must be submitted as a UTF-8 string",
            ) from exc
    if isinstance(value, str):
        return value
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        f"{field} must be submitted as a string",
    )


def _normalize_context(data: dict[str, Any]) -> dict[str, Any]:
    _enforce_mapping_constraints(data, field="context")
    return data


def _normalize_replacement_mapping(mapping: Mapping[str, Any]) -> dict[str, str]:
    """Validate and normalize replacement mappings."""

    if any(not isinstance(v, str) for v in mapping.values()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "replacements values must be strings")

    coerced = {str(k): v for k, v in mapping.items()}
    _enforce_mapping_constraints(coerced, field="replacements")
    return coerced


def _parse_replacements(raw: str) -> dict[str, str]:
    """Parse replacements payload originating from a multipart form."""

    data = _parse_json_object(raw, field="replacements")
    return _normalize_replacement_mapping(data)


def _coerce_replacements(data: dict[str, Any] | None) -> dict[str, str] | None:
    if data is None:
        return None

    return _normalize_replacement_mapping(data)


def _normalize_output_basename(value: str | None) -> str | None:
    try:
        return normalize_output_basename(value)
    except PayloadConstraintError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


async def _extract_json_payload(request: Request) -> PipelineRunPayload | None:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None

    body = await request.body()
    if not body.strip():
        return None

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Request body must be valid JSON",
        ) from exc

    try:
        return PipelineRunPayload.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


async def _resolve_pipeline_request(
    request: Request, payload: PipelineRunPayload | None
) -> PipelineRunRequestData:
    """Normalize pipeline payload coming either from JSON body or multipart form."""

    if payload is not None:
        context = _normalize_context(payload.context)
        return PipelineRunRequestData(
            context=context,
            replacements=_coerce_replacements(payload.replacements),
            header_text=payload.header_text,
            footer_text=payload.footer_text,
            idempotency_key=payload.idempotency_key,
            output_basename=_normalize_output_basename(payload.output_basename),
        )

    form = await request.form()
    context_raw = form.get("context")
    if context_raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "context is required")
    context_payload = _ensure_form_string(context_raw, field="context")

    replacements_value = form.get("replacements")
    if replacements_value is not None:
        replacements_raw = _ensure_form_string(replacements_value, field="replacements")
        replacements_data = _parse_replacements(replacements_raw)
    else:
        replacements_data = None

    return PipelineRunRequestData(
        context=_normalize_context(_parse_json_object(context_payload, field="context")),
        replacements=replacements_data,
        header_text=form.get("header_text"),
        footer_text=form.get("footer_text"),
        idempotency_key=form.get("idempotency_key"),
        output_basename=_normalize_output_basename(form.get("output_basename")),
    )


@router.get("/employees", response_model=PersonPage)
async def get_employees(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PersonPage:
    """List people registered under the active tenant."""

    persons, total = await list_persons(session, tenant.id, limit=limit, offset=offset)
    return PersonPage(items=persons, total=total)


@router.get("/templates", response_model=TemplatePage)
async def get_templates(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TemplatePage:
    """Return template metadata for the active tenant."""

    templates, total = await list_templates(
        session,
        tenant.slug,
        limit=limit,
        offset=offset,
        with_total=True,
    )
    return TemplatePage(items=templates, total=total)


@router.post("/templates", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_template(
    file: UploadDocx,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    name: Annotated[str, Form()],
    description: str | None = Form(None),
    metadata: str | None = Form(None),
    document_type: str = Form(...),
    required_fields_schema: str = Form(...),
    applicability_rules: str | None = Form(None),
    output_types: str = Form(...),
    profile: str | None = Form(None),
) -> dict[str, str]:
    """Persist a DOCX template and metadata in the database."""
    storage = FileStorageService.default()
    payload_bytes = await file.read(MAX_TEMPLATE_SIZE_BYTES + 1)
    if not payload_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Template file cannot be empty")
    if len(payload_bytes) > MAX_TEMPLATE_SIZE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Template file cannot exceed {MAX_TEMPLATE_SIZE_BYTES} bytes",
        )

    metadata_raw = metadata or ""
    if metadata_raw:
        metadata_bytes = metadata_raw.strip().encode("utf-8")
        if len(metadata_bytes) > MAX_METADATA_JSON_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"metadata payload cannot exceed {MAX_METADATA_JSON_BYTES} bytes",
            )

    metadata_payload = _parse_json_object(metadata, field="metadata")
    required_schema_payload = _parse_json_object(
        required_fields_schema, field="required_fields_schema"
    )
    applicability_payload = _parse_json_object(
        applicability_rules, field="applicability_rules"
    )
    output_types_payload = _parse_json_list(output_types, field="output_types")
    profile_payload = _parse_json_object(profile, field="profile")
    checksum = hashlib.sha256(payload_bytes).digest()
    payload = TemplateCreate(name=name, description=description, metadata=metadata_payload)
    try:
        version_metadata = TemplateVersionMetadata(
            document_type=document_type,
            required_fields_schema=required_schema_payload,
            applicability_rules=applicability_payload,
            output_types=output_types_payload,
            profile=profile_payload,
        )
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"template version metadata is invalid: {exc.errors()[0]['msg']}",
        ) from exc

    tenant_slug = tenant.slug

    existing = await get_active_template_with_version(session, payload.name, tenant_slug)
    if existing:
        template, version = existing
        if (
            template.description != payload.description
            or template.metadata_json != payload.metadata
            or version.checksum != checksum
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Template with this name already exists")
        response.status_code = status.HTTP_200_OK
        return {"id": template.id, "version_id": version.id}

    safe_name = Path(file.filename or "template.docx").name or "template.docx"
    if not safe_name.lower().endswith(".docx"):
        safe_name = f"{safe_name}.docx"

    template_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    prefix = build_dated_prefix(tenant_slug, now=now)
    key = f"{prefix}/templates/{template_id}/{safe_name}"

    storage.put(key, payload_bytes, content_type=DOCX_CONTENT_TYPE)
    try:
        version = await create_template_record(
            session,
            payload,
            storage_key=key,
            checksum=checksum,
            version_metadata=version_metadata,
            template_id=template_id,
            tenant_slug=tenant_slug,
        )
    except ValueError as exc:
        storage.delete(key)
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    created_new = version.template_id == template_id
    if not created_new:
        storage.delete(key)

    await session.commit()
    await session.refresh(version)

    if created_new:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK
    return {"id": version.template_id, "version_id": version.id}


@router.delete(
    "/templates/{template_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_template_version(
    template_id: str,
    version_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
) -> Response:
    tenant_scope = _tenant_scope(tenant)
    version = await session.get(TemplateVersion, version_id)
    if version is None or version.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    if version.tenant_id not in tenant_scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")

    if await _template_version_in_use(
        session, tenant=tenant, template_version_id=version.id
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Template version is already used and cannot be deleted",
        )

    await session.delete(version)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
) -> Response:
    tenant_scope = _tenant_scope(tenant)
    template = await session.get(Template, template_id)
    if template is None or template.tenant_id not in tenant_scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    if await _template_in_use(session, tenant=tenant, template_id=template.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Template is already used and cannot be deleted",
        )

    await session.execute(
        delete(TemplateVersion).where(TemplateVersion.template_id == template.id)
    )
    await session.delete(template)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/docx/mass-replace")
async def docx_mass_replace(
    file: UploadDocx,
    replacements: Annotated[str, Form()],
    tenant: TenantDep,
    access: EditorAccess,
):
    """Replace placeholders in the supplied DOCX and stream the result back."""
    data = await file.read()
    mapping = _parse_replacements(replacements)
    result = DocxService.mass_replace(data, mapping)

    return StreamingResponse(
        BytesIO(result),
        media_type=DOCX_CONTENT_TYPE,
        headers={"Content-Disposition": ATTACHMENT_HEADER.format(filename="mass-replace.docx")},
    )


@router.post("/docx/headers")
async def docx_headers(
    file: UploadDocx,
    tenant: TenantDep,
    access: EditorAccess,
    header_text: str | None = Form(None),
    footer_text: str | None = Form(None),
):
    """Apply header and footer text to a DOCX document."""
    data = await file.read()
    result = DocxService.set_headers_footers(data, header_text, footer_text)

    return StreamingResponse(
        BytesIO(result),
        media_type=DOCX_CONTENT_TYPE,
        headers={"Content-Disposition": ATTACHMENT_HEADER.format(filename="headers.docx")},
    )


@router.post("/pipelines/{template_id}/run", response_model=PipelineRunRead)
async def run_pipeline(
    template_id: str,
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    response: Response,
    payload: Annotated[PipelineRunPayload | None, Depends(_extract_json_payload)],
    mode: Annotated[str, Query(pattern="^(?:async|sync)$")] = "async",
) -> PipelineRunRead:
    """Execute document generation pipeline for the provided template."""
    tenant_slug = tenant.slug

    template_stmt = select(Template).where(
        Template.id == template_id,
        Template.tenant_id == tenant_slug,
    )
    template = (await session.execute(template_stmt)).scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    version_stmt = (
        select(TemplateVersion)
        .where(
            TemplateVersion.template_id == template.id,
            TemplateVersion.status == TemplateVersionStatus.ACTIVE,
        )
        .order_by(TemplateVersion.version.desc())
    )
    template_version = (await session.execute(version_stmt)).scalar_one_or_none()
    if not template_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Template has no active version")

    normalized = await _resolve_pipeline_request(request, payload)

    service = PipelineService()
    run_mode = mode.lower()
    effective_idempotency_key = normalized.idempotency_key or str(uuid.uuid4())
    try:
        if run_mode == "sync":
            run = await service.run(
                session=session,
                template=template,
                template_version=template_version,
                context=normalized.context,
                replacements=normalized.replacements,
                header_text=normalized.header_text,
                footer_text=normalized.footer_text,
                idempotency_key=effective_idempotency_key,
                output_basename=normalized.output_basename,
                tenant_id=tenant_slug,
            )
            response.status_code = status.HTTP_200_OK
            return PipelineRunRead.model_validate(run)

        run, _created = await service.ensure_pending_run(
            session,
            template=template,
            template_version=template_version,
            context=normalized.context,
            replacements=normalized.replacements,
            header_text=normalized.header_text,
            footer_text=normalized.footer_text,
            idempotency_key=effective_idempotency_key,
            output_basename=normalized.output_basename,
            tenant_id=tenant_slug,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await session.commit()
    await session.refresh(run)

    if run.status == PipelineRunStatus.QUEUED:
        try:
            trace_id = get_trace_id()
            run_pipeline_task.apply_async(
                args=[run.id, tenant_slug],
                kwargs={"tenant_slug": tenant_slug},
                task_id=run.id,
                headers={"trace_id": trace_id},
            )
        except Exception as exc:  # pragma: no cover - exercised in integration tests
            logger.warning("Falling back to synchronous pipeline execution", exc_info=exc)
            run = await service.run(
                session=session,
                template=template,
                template_version=template_version,
                context=normalized.context,
                replacements=normalized.replacements,
                header_text=normalized.header_text,
                footer_text=normalized.footer_text,
                idempotency_key=effective_idempotency_key,
                output_basename=normalized.output_basename,
                tenant_id=tenant_slug,
            )
            response.status_code = status.HTTP_200_OK
            return PipelineRunRead.model_validate(run)
        response.status_code = status.HTTP_202_ACCEPTED
        return PipelineRunRead.model_validate(run)

    response.status_code = status.HTTP_200_OK
    return PipelineRunRead.model_validate(run)
