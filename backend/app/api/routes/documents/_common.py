"""Documents API — shared foundation (ARCH-4 slice 5 split).

The single ``router`` instance plus error helpers, access dependencies, constants
and request/response models shared by the read and generate endpoint modules.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.screen_access import screen_roles
from app.core.security import abac, rbac
from app.models.models import (
    Tenant,
)
from app.modules.branding.schemas import LetterheadOverride

router = APIRouter()
logger = logging.getLogger(__name__)


def _generate_internal_error_problem() -> dict[str, Any]:
    """Клиентский ответ и тело для idempotency store без утечки внутренних исключений."""

    return api_problem_detail(
        code="INTERNAL_ERROR",
        message="Произошла внутренняя ошибка при обработке запроса.",
        error_type="server",
    )


def _documents_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(
            code="DOCUMENTS_BAD_REQUEST",
            message=message,
            error_type="documents",
        ),
    )


def _documents_not_found(*, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(code=code, message=message, error_type="documents"),
    )


def _documents_conflict(
    message: str,
    *,
    code: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code=code, message=message, error_type="documents", details=details
        ),
    )


def _documents_forbidden(*, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(code=code, message=message, error_type="documents"),
    )


def _documents_payload_too_large(
    message: str, *, code: str = "DOCUMENT_PAYLOAD_TOO_LARGE"
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=api_problem_detail(code=code, message=message, error_type="documents"),
    )


def _dispatch_celery_task(
    task,
    *,
    args: list[str],
    kwargs: dict[str, str],
    task_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    task.apply_async(args=args, kwargs=kwargs, task_id=task_id, headers=headers)


SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_DOCUMENT_RUN_ROLES = list(screen_roles("doc.create"))
# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_DOCUMENT_READ_ROLES = list(screen_roles("doc.view"))
_DOCUMENT_STATUS_ROLES = ["admin"]
_DEFAULT_DOCUMENT_PIPELINE_PROFILE = "default_doc_pipeline"

AccessDep = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_DOCUMENT_RUN_ROLES,
        action="manage documents",
    )
)
ReadAccessDep = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_DOCUMENT_READ_ROLES,
        action="read documents",
    )
)
StatusAccessDep = Depends(rbac(_DOCUMENT_STATUS_ROLES))


class GenerateTemplateRef(BaseModel):
    code: str
    version: int


class GenerateDataPayload(BaseModel):
    type: str
    payload: dict[str, Any] | None = None
    file_id: str | None = None


class GenerateStepOptions(BaseModel):
    apply_headers: dict[str, Any] | None = None
    replace: dict[str, Any] | None = None
    pdf: dict[str, Any] | None = None
    zip: dict[str, Any] | None = None


class GeneratePipelinePayload(BaseModel):
    profile_code: str | None = None
    steps: GenerateStepOptions | None = None


class DocGeneratePipelineRequest(BaseModel):
    template: GenerateTemplateRef
    data: GenerateDataPayload
    pipeline: GeneratePipelinePayload | None = None
    npa_binding_id: str | None = None


class DocGenerateRequest(BaseModel):
    """Incoming payload for document generation requests."""

    model_config = ConfigDict(extra="forbid")

    template_code: str | None = Field(default=None, min_length=1, max_length=255)
    template_id: str | None = Field(default=None, min_length=1)
    template_version: int | None = Field(default=None, ge=1)
    company_id: str | None = Field(default=None, min_length=1)
    person_id: str | None = Field(default=None)
    data: dict[str, Any] = Field(default_factory=dict)
    pipeline_profile_id: str | None = Field(default=None)
    input_source_id: str | None = Field(default=None)
    inline_data: dict[str, Any] | None = Field(default=None)
    options: dict[str, Any] = Field(default_factory=dict)
    visible_passport: bool = Field(default=True)
    npa_binding_id: str | None = Field(default=None)
    letterhead: LetterheadOverride | None = Field(default=None)

    @model_validator(mode="after")
    def _ensure_identifier(self) -> "DocGenerateRequest":
        if not self.template_code:
            raise ValueError("template_code is required to select a template")
        if self.template_version is None:
            raise ValueError("template_version is required to select a template")
        if self.inline_data is None and self.input_source_id is None and self.company_id is None:
            raise ValueError("company_id required for legacy mode")
        return self


class DocumentQualityCheckRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    date_fields: list[str] = Field(default_factory=list)
    numeric_fields: list[str] = Field(default_factory=list)
    rendered_text: str | None = None


class DocumentMappingValidateRequest(BaseModel):
    source_fields: list[str] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)
    required_template_fields: list[str] = Field(default_factory=list)


class TemplateResolveRequest(BaseModel):
    case_type: str | None = Field(default=None, min_length=1, max_length=255)
    document_type: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=255)
    company_id: str | None = Field(default=None, min_length=1)
    site_id: str | None = Field(default=None, min_length=1)
    person_id: str | None = Field(default=None, min_length=1)


class TemplateResolveCandidateRead(BaseModel):
    template_id: str
    template_code: str
    template_name: str
    template_version: int
    scope_level: str
    scope_match: str
    score: int
    rationale: list[str] = Field(default_factory=list)


class TemplateResolveResponse(BaseModel):
    template_id: str
    template_code: str
    template_name: str
    template_version: int
    scope_level: str
    resolution_chain: list[str] = Field(default_factory=list)
    alternatives: list[TemplateResolveCandidateRead] = Field(default_factory=list)
