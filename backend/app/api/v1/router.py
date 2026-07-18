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
from time import perf_counter
from typing import Annotated, Any, Mapping
from uuid import UUID

from fastapi import (
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.v1.route_groups import create_public_router, create_tenant_router
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.core.payload_constraints import (
    PayloadConstraintError,
    enforce_mapping_constraints,
    normalize_output_basename,
)
from app.core.security import AccessContext, abac
from app.core.tracing import get_trace_id
from app.models.document import Document
from app.models.document_core import (
    DocumentPackItem,
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateStatus,
    TemplateUsage,
    TemplateVersion,
    TemplateVersionStatus,
)
from app.models.tenanting import Tenant
from app.modules.templates import (
    build_passport,
    inspect_template_variables,
from app.modules.files.utils import build_dated_prefix
from app.modules.templates import (
    audit_template_versions,
    build_passport,
    inspect_docx_template,
    lint_docx_template,
    render_preview_docx,
)
from app.modules.templates.repo import get_template_version_by_code
from app.modules.templates.schemas import (
    InspectorReportDTO,
    InspectorRequest,
    LintReportDTO,
    LintRequest,
    PreviewRequest,
    PreviewResponse,
    RenderPreviewRequest,
    RenderPreviewResponse,
    TemplateAuditReportDTO,
    TemplateCreateRequest,
    TemplateDTO,
    TemplatePatchRequest,
    TemplateVariableInspectorDTO,
    TemplateVersionDTO,
)
from app.modules.tenancy.helpers import tenant_s3_key
from app.repository import (
    create_template as create_template_record,
)
from app.repository import (
    get_active_template_with_version,
    list_persons,
    list_templates,
)
from app.schemas.common import PipelineRunRead, TemplatePage
from app.schemas.person import PersonPage
from app.schemas.template import TemplateCreate, TemplateVersionMetadata
from app.services.audit import AuditService, field_level_diff
from app.services.billing import BillingService
from app.services.docx import DocxService
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.pipeline import PipelineService
from app.services.tasks import run_pipeline_task
from app.tenancy_quotas import assert_quota

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ATTACHMENT_HEADER = 'attachment; filename="{filename}"'

UploadDocx = Annotated[UploadFile, File(media_type=DOCX_CONTENT_TYPE)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
_MANAGERIAL_ROLES = ["admin"]
_EDITOR_ROLES = ["admin"]
_TEMPLATE_SCOPE_ORDER = {
    "branch": 0,
    "site": 0,
    "organization": 1,
    "legal_entity": 1,
    "tenant": 2,
    "global": 3,
    "system": 3,
}


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

router = create_public_router()
tenant_router = create_tenant_router()

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


async def _enforce_tenant_generation_quota(session: AsyncSession, tenant: Tenant) -> None:
    """Apply the canonical quota checks used by pipeline generation entrypoints."""

    await assert_quota(session, tenant=tenant, kind="jobs", delta=1)
    await assert_quota(session, tenant=tenant, kind="generations_month", delta=1)


def _template_scope_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    payload = metadata or {}
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    return {
        "type": str(scope.get("type") or scope.get("level") or "tenant"),
        "tenant_id": scope.get("tenant_id"),
        "company_id": scope.get("company_id"),
        "site_id": scope.get("site_id"),
        "label": scope.get("label"),
        "applicability": scope.get("applicability"),
    }


def _template_metadata_payload(
    *,
    category: str | None = None,
    scope: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if category:
        metadata["category"] = category
    normalized_scope = _template_scope_from_metadata({"scope": scope or {}})
    metadata["scope"] = normalized_scope
    if extra:
        metadata.update(extra)
    return metadata


def _template_to_dto(template: Template) -> TemplateDTO:
    metadata = template.metadata_json or {}
    payload = {
        "id": template.id,
        "code": template.code,
        "name": template.name,
        "description": template.description,
        "category": metadata.get("category"),
        "status": (
            template.status.value if hasattr(template.status, "value") else str(template.status)
        ),
        "scope": _template_scope_from_metadata(metadata),
        "current_version_id": template.current_version_id,
        "updated_at": template.updated_at,
        "created_at": template.created_at,
        "version": template.version,
    }
    return TemplateDTO.model_validate(payload)


def _tenant_scope(tenant: Tenant) -> tuple[str, ...]:
    values = [tenant.slug]
    if getattr(tenant, "id", None):
        values.append(str(tenant.id))
    return tuple(values)


def _normalize_template_scope(
    raw_scope: Mapping[str, Any] | None,
    *,
    tenant: Tenant,
    company_id: str | None = None,
    site_id: str | None = None,
) -> dict[str, Any]:
    payload = dict(raw_scope or {})
    scope_type = str(payload.get("level") or payload.get("type") or "tenant").strip().lower()
    if scope_type == "branch":
        scope_type = "site"
    if scope_type not in {"global", "system", "tenant", "legal_entity", "organization", "site"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported template scope")
    payload["level"] = scope_type
    payload["type"] = scope_type
    payload["tenant_id"] = str(payload.get("tenant_id") or tenant.slug)
    if scope_type in {"legal_entity", "organization"}:
        payload["company_id"] = company_id or payload.get("company_id")
    if scope_type == "site":
        payload["company_id"] = company_id or payload.get("company_id")
        payload["site_id"] = site_id or payload.get("site_id")
    return payload


def _extract_scope_from_template(template: Template) -> dict[str, Any]:
    # Prefer normalized columns when available.
    level = getattr(template, "scope_level", None) or "tenant"
    company_id = getattr(template, "scope_company_id", None)
    site_id = getattr(template, "scope_site_id", None)
    if company_id or site_id or level:
        return {
            "type": level,
            "tenant_id": template.tenant_id,
            "company_id": company_id,
            "site_id": site_id,
        }
    metadata = dict(template.metadata_json or {})
    return dict(metadata.get("scope") or {"type": "tenant", "tenant_id": template.tenant_id})


def _template_type(template: Template) -> str | None:
    metadata = dict(template.metadata_json or {})
    return getattr(template, "domain", None) or metadata.get("template_type")


def _build_template_dto(template: Template, *, include_versions: bool = False) -> TemplateDTO:
    versions = sorted(
        [
            item
            for item in getattr(template, "versions", [])
            if getattr(item, "deleted_at", None) is None
        ],
        key=lambda item: item.version,
        reverse=True,
    )
    current_version = next(
        (item for item in versions if item.id == template.current_version_id), None
    )
    if current_version is None and versions:
        current_version = versions[0]
    return TemplateDTO.model_validate(
        {
            "id": template.id,
            "code": template.code,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "status": (
                template.status.value if hasattr(template.status, "value") else str(template.status)
            ),
            "current_version_id": template.current_version_id,
            "updated_at": template.updated_at,
            "created_at": template.created_at,
            "version": template.version,
            "metadata_json": template.metadata_json or {},
            "template_type": _template_type(template),
            "scope": _extract_scope_from_template(template),
            "current_version": (
                TemplateVersionDTO.model_validate(current_version) if current_version else None
            ),
            "versions": (
                [TemplateVersionDTO.model_validate(item) for item in versions]
                if include_versions
                else []
            ),
        }
    )


async def _template_version_in_use(
    session: AsyncSession,
    *,
    tenant: Tenant,
    template_version_id: str,
) -> bool:
    tenant_scope = _tenant_scope(tenant)
    document_count = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.template_version_id == template_version_id,
            Document.tenant_id.in_(tenant_scope),
        )
    )
    pipeline_count = await session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(
            PipelineRun.template_version_id == template_version_id,
            PipelineRun.tenant_id.in_(tenant_scope),
        )
    )
    pack_count = await session.scalar(
        select(func.count())
        .select_from(DocumentPackItem)
        .where(
            DocumentPackItem.template_version_id == template_version_id,
            DocumentPackItem.tenant_id.in_(tenant_scope),
        )
    )
    usage_count = await session.scalar(
        select(func.count())
        .select_from(TemplateUsage)
        .where(
            TemplateUsage.template_version_id == template_version_id,
            TemplateUsage.tenant_id.in_(tenant_scope),
        )
    )
    return any(
        count and count > 0 for count in (document_count, pipeline_count, pack_count, usage_count)
    )


async def _template_in_use(
    session: AsyncSession,
    *,
    tenant: Tenant,
    template_id: str,
) -> bool:
    tenant_scope = _tenant_scope(tenant)
    document_count = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.template_id == template_id,
            Document.tenant_id.in_(tenant_scope),
        )
    )
    pipeline_count = await session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(
            PipelineRun.template_id == template_id,
            PipelineRun.tenant_id.in_(tenant_scope),
        )
    )
    pack_count = await session.scalar(
        select(func.count())
        .select_from(DocumentPackItem)
        .where(
            DocumentPackItem.template_id == template_id,
            DocumentPackItem.tenant_id.in_(tenant_scope),
        )
    )
    return any(count and count > 0 for count in (document_count, pipeline_count, pack_count))


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
    status_value: str | None = Query(default=None, alias="status"),
    document_type: str | None = Query(default=None),
    company_id: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
) -> TemplatePage:
    """Return template metadata for the active tenant."""

    templates, total = await list_templates(
        session,
        tenant.slug,
        limit=limit,
        offset=offset,
        with_total=True,
    )
    filtered: list[TemplateDTO] = []
    for template in templates:
        dto = _build_template_dto(template)
        if status_value and dto.status != status_value:
            continue
        if document_type and dto.template_type != document_type:
            current_document_type = (
                dto.current_version.document_type if dto.current_version else None
            )
            if current_document_type != document_type:
                continue
        scope = dto.scope or {}
        if company_id and scope.get("company_id") not in {None, company_id}:
            continue
        if site_id and scope.get("site_id") not in {None, site_id}:
            continue
        filtered.append(dto)
    return TemplatePage(items=filtered, total=len(filtered))


@router.post("/templates/catalog", response_model=TemplateDTO, status_code=status.HTTP_201_CREATED)
async def create_template_catalog(
    payload: TemplateCreateRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
) -> TemplateDTO:
    normalized_scope = _normalize_template_scope(
        payload.scope.model_dump(mode="json"),
        tenant=tenant,
        company_id=payload.scope.company_id,
        site_id=payload.scope.site_id,
    )
    template = Template(
        tenant_id=str(tenant.id),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        status=TemplateStatus(payload.status or TemplateStatus.DRAFT.value),
        domain=payload.template_type,
        category=payload.category,
        scope_level=str(normalized_scope.get("level") or normalized_scope.get("type") or "tenant"),
        scope_company_id=normalized_scope.get("company_id"),
        scope_site_id=normalized_scope.get("site_id"),
        metadata_json=_template_metadata_payload(
            category=payload.category,
            scope=normalized_scope,
            extra={"template_type": payload.template_type} if payload.template_type else None,
        ),
    )
    session.add(template)
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="template",
        object_id=template.id,
        user_id=getattr(access, "user_id", None),
        ip=request.client.host if request.client else "unknown",
        request_id=get_trace_id(request),
        user_agent=request.headers.get("user-agent"),
        changed_fields={"after": {"code": template.code, "name": template.name}},
    )
    await session.commit()
    await session.refresh(template, ["versions"])
    return _build_template_dto(template, include_versions=True)


@router.get("/templates/{template_id}", response_model=TemplateDTO)
async def get_template_details(
    template_id: str, session: SessionDep, tenant: TenantDep, access: ManagerAccess
) -> TemplateDTO:
    template = await session.get(Template, template_id)
    if (
        template is None
        or template.tenant_id not in _tenant_scope(tenant)
        or template.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return _build_template_dto(template, include_versions=True)


@router.patch("/templates/{template_id}", response_model=TemplateDTO)
async def patch_template(
    template_id: str,
    payload: TemplatePatchRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
) -> TemplateDTO:
    template = await session.get(Template, template_id)
    if (
        template is None
        or template.tenant_id not in _tenant_scope(tenant)
        or template.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    before = {
        "code": template.code,
        "name": template.name,
        "description": template.description,
        "status": str(template.status),
        "current_version_id": template.current_version_id,
        "version": template.version,
        "domain": template.domain,
        "metadata_json": dict(template.metadata_json or {}),
    }
    if payload.version is not None and payload.version != template.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "optimistic_lock_mismatch",
                "type": "conflict",
                "message": "template version mismatch",
            },
        )
    for key in ("code", "name", "description", "current_version_id"):
        value = getattr(payload, key)
        if value is not None:
            setattr(template, key, value)
    if payload.status is not None:
        template.status = TemplateStatus(payload.status)
    metadata = dict(template.metadata_json or {})
    if payload.category is not None:
        metadata["category"] = payload.category
        template.category = payload.category
    template.metadata_json = metadata
    if payload.template_type is not None:
        template.domain = payload.template_type
        template.metadata_json = {
            **(template.metadata_json or {}),
            "template_type": payload.template_type,
        }
    if payload.scope is not None:
        normalized_scope = _normalize_template_scope(
            payload.scope.model_dump(mode="json"),
            tenant=tenant,
            company_id=payload.scope.company_id,
            site_id=payload.scope.site_id,
        )
        template.scope_level = str(
            normalized_scope.get("level") or normalized_scope.get("type") or "tenant"
        )
        template.scope_company_id = normalized_scope.get("company_id")
        template.scope_site_id = normalized_scope.get("site_id")
        template.metadata_json = {
            **(template.metadata_json or {}),
            "scope": normalized_scope,
        }
    await session.flush()
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="template",
        object_id=template.id,
        user_id=getattr(access, "user_id", None),
        ip=request.client.host if request.client else "unknown",
        request_id=get_trace_id(request),
        user_agent=request.headers.get("user-agent"),
        changed_fields=field_level_diff(
            before,
            {
                "name": template.name,
                "description": template.description,
                "status": str(template.status),
                "current_version_id": template.current_version_id,
                "version": template.version,
                "metadata_json": dict(template.metadata_json or {}),
            },
        ),
    )
    await session.commit()
    await session.refresh(template)
    return _build_template_dto(template, include_versions=True)


@router.post(
    "/templates/{template_id}/versions:upload",
    response_model=TemplateVersionDTO,
    status_code=status.HTTP_201_CREATED,
)
async def upload_template_version(
    template_id: str,
    file: UploadDocx,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
    response: Response,
    document_type: str | None = Form(default=None),
    applicability_rules: str | None = Form(default=None),
    output_types: str | None = Form(default=None),
    profile: str | None = Form(default=None),
    status_value: str = Form(default=TemplateVersionStatus.UPLOADED.value),
) -> TemplateVersionDTO:
    template = await session.get(Template, template_id)
    if (
        template is None
        or template.tenant_id not in _tenant_scope(tenant)
        or template.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    payload_bytes = await file.read()
    idempotency_key = request.headers.get("Idempotency-Key")
    idem_service = None
    idem_record = None
    if idempotency_key:
        normalized = normalize_idempotency_key(idempotency_key)
        idem_service = IdempotencyService(
            session=session, tenant_id=str(tenant.id), endpoint=f"template_upload:{template_id}"
        )
        idem_record, created = await idem_service.acquire(
            key=normalized,
            request_hash=hashlib.sha256(payload_bytes).hexdigest(),
            method=request.method,
            path=str(request.url.path),
        )
        if not created:
            return await idem_service.respond_from_store(
                idem_record, model=TemplateVersionDTO, response=response
            )
    sha = hashlib.sha256(payload_bytes).hexdigest()
    next_ver = int(
        (
            await session.scalar(
                select(func.max(TemplateVersion.version)).where(
                    TemplateVersion.template_id == template.id
                )
            )
            or 0
        )
        + 1
    )
    key = tenant_s3_key(
        tenant.slug,
        f"templates/{template.id}/v{next_ver}/{Path(file.filename or 'template.docx').name}",
    )
    storage = FileStorageService.default()
    storage.put(key, payload_bytes, content_type=DOCX_CONTENT_TYPE)
    parsed = lint_docx_template(payload_bytes)
    version = TemplateVersion(
        tenant_id=str(tenant.id),
        template_id=template.id,
        version=next_ver,
        checksum=hashlib.sha256(payload_bytes).digest(),
        sha256=sha,
        status=TemplateVersionStatus(status_value),
        payload_key=key,
        file_id=key,
        size_bytes=len(payload_bytes),
        placeholder_index=parsed.get("placeholders_json"),
        linter_report_json=parsed,
        document_type=document_type or template.domain,
        applicability_rules=_parse_json_object(applicability_rules, field="applicability_rules"),
        output_types=_parse_json_list(output_types, field="output_types") if output_types else None,
        profile=_parse_json_object(profile, field="profile"),
    )
    session.add(version)
    await session.flush()
    template.current_version_id = version.id
    dto = TemplateVersionDTO.model_validate(version)
    if idem_service and idem_record:
        await idem_service.store_success(
            idem_record,
            status_code=status.HTTP_201_CREATED,
            body=dto.model_dump(mode="json", by_alias=True),
        )
    await session.commit()
    await session.refresh(version)
    return TemplateVersionDTO.model_validate(version)


@router.post("/templates/{template_id}/versions/{version_id}:lint", response_model=LintReportDTO)
async def lint_template_version(
    template_id: str,
    version_id: str,
    payload: LintRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
) -> LintReportDTO:
    version = await session.get(TemplateVersion, version_id)
    if (
        version is None
        or version.template_id != template_id
        or version.tenant_id not in _tenant_scope(tenant)
        or version.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    storage = FileStorageService.default()
    source = storage.get(version.file_id or version.payload_key)
    report = lint_docx_template(
        source,
        required_fields=payload.required_fields,
        sample_schema=payload.sample_schema,
    )
    version.placeholder_index = report.get("placeholders_json")
    version.linter_report_json = report
    version.status = (
        TemplateVersionStatus.READY if not report.get("errors") else TemplateVersionStatus.LINTED
    )
    await session.commit()
    return LintReportDTO.model_validate(report)


@router.get(
    "/templates/{template_id}/versions/{version_id}/variables",
    response_model=TemplateVariableInspectorDTO,
    summary="Variable inspector: used vs declared variables for a template version",
)
async def inspect_template_version_variables(
    template_id: str,
    version_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
) -> TemplateVariableInspectorDTO:
@router.post(
    "/templates/{template_id}/versions/{version_id}:inspect",
    response_model=InspectorReportDTO,
)
async def inspect_template_version(
    template_id: str,
    version_id: str,
    payload: InspectorRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
) -> InspectorReportDTO:
    version = await session.get(TemplateVersion, version_id)
    if (
        version is None
        or version.template_id != template_id
        or version.tenant_id not in _tenant_scope(tenant)
        or version.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    report = inspect_template_variables(
        placeholder_index=version.placeholder_index,
        required_fields_schema=version.required_fields_schema,
    )
    return TemplateVariableInspectorDTO.model_validate(report)


@router.post("/templates/{template_id}/versions/{version_id}:preview", response_model=PreviewResponse)
    storage = FileStorageService.default()
    source = storage.get(version.file_id or version.payload_key)
    report = inspect_docx_template(
        source,
        available_variables=payload.available_variables,
        required_fields=payload.required_fields,
    )
    return InspectorReportDTO.model_validate(report)


@router.get(
    "/templates:audit",
    response_model=TemplateAuditReportDTO,
    summary="Bulk audit of every template version in the tenant",
)
async def audit_tenant_templates(
    session: SessionDep,
    tenant: TenantDep,
    access: ManagerAccess,
    template_id: str | None = Query(default=None),
) -> TemplateAuditReportDTO:
    """Run the hardened linter against every non-deleted template version
    in the current tenant and return a structured report. Admin-only.
    """
    storage = FileStorageService.default()
    report = await audit_template_versions(
        session,
        tenant_id=str(tenant.id),
        loader=storage.get,
        template_id=template_id,
    )
    return TemplateAuditReportDTO.model_validate(report.to_dict())


@router.post(
    "/templates/{template_id}/versions/{version_id}:preview", response_model=PreviewResponse
)
async def preview_template_version(
    template_id: str,
    version_id: str,
    payload: PreviewRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
) -> PreviewResponse:
    version = await session.get(TemplateVersion, version_id)
    if (
        version is None
        or version.template_id != template_id
        or version.tenant_id not in _tenant_scope(tenant)
        or version.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    storage = FileStorageService.default()
    source = storage.get(version.file_id or version.payload_key)
    idempotency_key = request.headers.get("Idempotency-Key")
    idem_service = None
    idem_record = None
    if idempotency_key:
        normalized = normalize_idempotency_key(idempotency_key)
        idem_service = IdempotencyService(
            session=session,
            tenant_id=str(tenant.id),
            endpoint=f"template_preview:{template_id}:{version_id}",
        )
        idem_record, created = await idem_service.acquire(
            key=normalized,
            request_hash=hashlib.sha256(
                json.dumps(
                    payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
                ).encode("utf-8")
            ).hexdigest(),
            method=request.method,
            path=str(request.url.path),
        )
        if not created:
            return await idem_service.respond_from_store(idem_record, model=PreviewResponse)
    template = await session.get(Template, template_id)
    if (
        template is None
        or template.tenant_id not in _tenant_scope(tenant)
        or template.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    passport = build_passport(
        code=template.code or template.name,
        version=version.version,
        tenant_id=str(tenant.id),
        generated_by="api_user",
        correlation_id=get_trace_id(request),
        data=payload.data,
    )
    rendered = render_preview_docx(template_bytes=source, data=payload.data, passport=passport)
    out_key = tenant_s3_key(tenant.slug, f"templates/preview/{uuid.uuid4()}/preview.docx")
    storage.put(out_key, rendered, content_type=DOCX_CONTENT_TYPE)
    preview = PreviewResponse(
        job_id=str(uuid.uuid4()), status="done", docx_url=out_key, pdf_url=None
    )
    if idem_service and idem_record:
        await idem_service.store_success(
            idem_record, status_code=status.HTTP_200_OK, body=preview.model_dump(mode="json")
        )
        await session.commit()
    return preview


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
    await BillingService(session).assert_allowed(tenant, "templates.create")
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
    applicability_payload = _parse_json_object(applicability_rules, field="applicability_rules")
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


@router.post(
    "/templates/{template_id}/versions", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def create_template_version(
    template_id: str,
    file: UploadDocx,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    status_value: str = Form("active"),
) -> dict[str, str]:
    template = await session.get(Template, template_id)
    if (
        template is None
        or template.tenant_id not in _tenant_scope(tenant)
        or template.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    await BillingService(session).assert_allowed(tenant, "templates.create")
    payload = await file.read(MAX_TEMPLATE_SIZE_BYTES + 1)
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Template file cannot be empty")
    checksum_hex = hashlib.sha256(payload).hexdigest()
    lint = lint_docx_template(payload)

    last_ver_stmt = select(func.coalesce(func.max(TemplateVersion.version), 0)).where(
        TemplateVersion.template_id == template.id
    )
    next_ver = int(await session.scalar(last_ver_stmt) or 0) + 1
    key = tenant_s3_key(
        tenant.slug,
        f"templates/{template.code or template.name}/v{next_ver}/template.docx",
    )
    FileStorageService.default().put(key, payload, content_type=DOCX_CONTENT_TYPE)

    version = TemplateVersion(
        tenant_id=str(tenant.id),
        template_id=template.id,
        version=next_ver,
        checksum=bytes.fromhex(checksum_hex),
        sha256=checksum_hex,
        status=TemplateVersionStatus(status_value),
        payload_key=key,
        file_id=key,
        placeholder_index=lint,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return {"id": version.id, "template_id": template.id, "version": str(version.version)}


@router.get("/templates/{template_id}/versions", response_model=list[dict])
async def list_template_versions(
    template_id: str, session: SessionDep, tenant: TenantDep, access: ManagerAccess
) -> list[dict[str, object]]:
    stmt = (
        select(TemplateVersion)
        .where(
            TemplateVersion.template_id == template_id,
            TemplateVersion.tenant_id.in_(_tenant_scope(tenant)),
            TemplateVersion.deleted_at.is_(None),
        )
        .order_by(TemplateVersion.version.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "status": r.status.value,
            "sha256": r.sha256,
            "file_id": r.file_id,
            "placeholder_index": r.placeholder_index,
        }
        for r in rows
    ]


@router.get("/templates/{template_id}/versions/{version_id}", response_model=TemplateVersionDTO)
async def get_template_version(
    template_id: str,
    version_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: ManagerAccess,
) -> TemplateVersionDTO:
    version = await session.get(TemplateVersion, version_id)
    if (
        version is None
        or version.template_id != template_id
        or version.tenant_id not in _tenant_scope(tenant)
        or version.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    return TemplateVersionDTO.model_validate(version)


@router.patch("/templates/{template_id}/versions/{version_id}", response_model=TemplateVersionDTO)
async def patch_template_version(
    template_id: str,
    version_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
) -> TemplateVersionDTO:
    version = await session.get(TemplateVersion, version_id)
    if (
        version is None
        or version.template_id != template_id
        or version.tenant_id not in _tenant_scope(tenant)
        or version.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    if "status" in payload:
        next_status = TemplateVersionStatus(str(payload["status"]).lower())
        if next_status == TemplateVersionStatus.ARCHIVED and await _template_version_in_use(
            session,
            tenant=tenant,
            template_version_id=version.id,
        ):
            template = await session.get(Template, template_id)
            if template is not None and template.current_version_id == version.id:
                template.current_version_id = None
        version.status = next_status
    if "document_type" in payload:
        version.document_type = str(payload["document_type"]) if payload["document_type"] else None
    if "applicability_rules" in payload and isinstance(payload["applicability_rules"], dict):
        version.applicability_rules = payload["applicability_rules"]
    if "output_types" in payload and isinstance(payload["output_types"], list):
        version.output_types = payload["output_types"]
    if "profile" in payload and isinstance(payload["profile"], dict):
        version.profile = payload["profile"]
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="template_version.update",
        object_type="template_version",
        object_id=version.id,
        user_id=getattr(access, "user_id", None),
        ip=request.client.host if request.client else "unknown",
        request_id=get_trace_id(request),
        user_agent=request.headers.get("user-agent"),
        changed_fields={
            "after": {"status": version.status.value, "document_type": version.document_type}
        },
    )
    await session.commit()
    await session.refresh(version)
    return TemplateVersionDTO.model_validate(version)


@router.get("/templates/by-code/{code}", response_model=dict)
async def get_template_by_code_version(
    code: str,
    session: SessionDep,
    tenant: TenantDep,
    access: ManagerAccess,
    request: Request,
    version: int = Query(..., ge=1),
) -> dict[str, object]:
    row = await get_template_version_by_code(
        session, tenant_id=str(tenant.id), code=code, version=version
    )
    if row is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "template_version_not_found",
                "type": "conflict",
                "message": "Template selection by (code, version) failed",
                "correlation_id": get_trace_id(request),
            },
        )
    template, tv = row
    return {
        "template_id": template.id,
        "code": template.code,
        "name": template.name,
        "version_id": tv.id,
        "version": tv.version,
        "status": tv.status.value,
        "file_id": tv.file_id,
    }


@router.post("/templates/render-preview", response_model=RenderPreviewResponse)
async def render_preview(
    payload: RenderPreviewRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
) -> RenderPreviewResponse:
    row = await get_template_version_by_code(
        session, tenant_id=str(tenant.id), code=payload.code, version=payload.version
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    template, tv = row
    storage = FileStorageService.default()
    source = storage.get(tv.file_id or tv.payload_key)
    correlation_id = get_trace_id(request)
    passport = build_passport(
        code=template.code,
        version=tv.version,
        tenant_id=str(tenant.id),
        generated_by="api_user",
        correlation_id=correlation_id,
        data=payload.data,
        options={"visible_passport": payload.visible_passport},
        npa_binding_id=payload.npa_binding_id,
    )
    rendered = render_preview_docx(
        template_bytes=source,
        data=payload.data,
        passport=passport,
        visible_passport=payload.visible_passport,
    )
    rendered_sha = hashlib.sha256(rendered).hexdigest()
    out_key = tenant_s3_key(tenant.slug, f"documents/preview/{uuid.uuid4()}/rendered.docx")
    storage.put(out_key, rendered, content_type=DOCX_CONTENT_TYPE)
    return RenderPreviewResponse(
        file_id=out_key,
        sha256=rendered_sha,
        passport=passport,
        warnings=tv.placeholder_index.get("errors", []) if tv.placeholder_index else [],
        generated_at=datetime.now(timezone.utc),
    )


@router.delete(
    "/templates/{template_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_template_version(
    template_id: str,
    version_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
    request: Request,
) -> None:
    tenant_scope = _tenant_scope(tenant)
    version = await session.get(TemplateVersion, version_id)
    if version is None or version.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")
    if version.tenant_id not in tenant_scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template version not found")

    if await _template_version_in_use(session, tenant=tenant, template_version_id=version.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "template_version_in_use",
                "type": "conflict",
                "message": "Template version is already used and cannot be deleted",
                "correlation_id": get_trace_id(request),
            },
        )

    version.deleted_at = datetime.now(timezone.utc)
    template = await session.get(Template, template_id)
    if template is not None and template.current_version_id == version.id:
        template.current_version_id = None
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="template_version.delete",
        object_type="template_version",
        object_id=version.id,
        user_id=getattr(access, "user_id", None),
        ip=request.client.host if request.client else "unknown",
        request_id=get_trace_id(request),
        user_agent=request.headers.get("user-agent"),
        details={"template_id": template_id, "deleted_at": version.deleted_at.isoformat()},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_template(
    template_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: EditorAccess,
) -> None:
    tenant_scope = _tenant_scope(tenant)
    template = await session.get(Template, template_id)
    if template is None or template.tenant_id not in tenant_scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    if await _template_in_use(session, tenant=tenant, template_id=template.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "template_in_use",
                "type": "conflict",
                "message": "Template is already used and cannot be deleted",
            },
        )

    has_versions = await session.scalar(
        select(func.count())
        .select_from(TemplateVersion)
        .where(TemplateVersion.template_id == template.id, TemplateVersion.deleted_at.is_(None))
    )
    if has_versions:
        raise HTTPException(status.HTTP_409_CONFLICT, "Template has versions; archive it instead")
    template.deleted_at = datetime.now(timezone.utc)
    template.status = TemplateStatus.ARCHIVED
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="template.delete",
        object_type="template",
        object_id=template.id,
        user_id=getattr(access, "user_id", None),
        ip="api",
        details={"archived": True, "deleted_at": template.deleted_at.isoformat()},
    )
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
    metrics = get_metrics()
    metrics.record_pipeline_stage_start(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.REQUEST_RECEIVED,
    )
    metrics.record_pipeline_stage_end(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.REQUEST_RECEIVED,
        result=StageResult.SUCCESS,
        seconds=0.0,
    )
    validation_start = perf_counter()
    metrics.record_pipeline_stage_start(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.VALIDATION_COMPLETED,
    )

    try:
        template_stmt = select(Template).where(
            Template.id == template_id,
            Template.tenant_id.in_(_tenant_scope(tenant)),
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
    except Exception as exc:
        metrics.record_pipeline_stage_end(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.VALIDATION_COMPLETED,
            result=StageResult.FAILED,
            seconds=perf_counter() - validation_start,
            error_class=exc.__class__.__name__,
        )
        raise
    metrics.record_pipeline_stage_end(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.VALIDATION_COMPLETED,
        result=StageResult.SUCCESS,
        seconds=perf_counter() - validation_start,
    )

    await _enforce_tenant_generation_quota(session, tenant)

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
                tenant_id=str(tenant.id),
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
            tenant_id=str(tenant.id),
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
                tenant_id=str(tenant.id),
            )
            response.status_code = status.HTTP_200_OK
            return PipelineRunRead.model_validate(run)
        response.status_code = status.HTTP_202_ACCEPTED
        return PipelineRunRead.model_validate(run)

    response.status_code = status.HTTP_200_OK
    return PipelineRunRead.model_validate(run)
