"""API прав субъекта ПДн (SEC-66 срез-1, разд. 66.2).

* ``GET /privacy/subjects/{person_id}/export``     — право на доступ к своим данным.
* ``GET /privacy/subjects/{person_id}/access-log`` — журнал: кто и когда их читал.

За фичефлагом ``pdn_subject_rights`` (**default-ON**, в отличие от пилотных
`budget`/`rules_engine`): это исполнение требования закона, а не пилот, поэтому
контур работает из коробки, а арендатор при желании выключается явной записью
`FeatureEnablement(on=False)`.

RBAC: `admin`/`owner`/`hr` — уже, чем чтение карточки сотрудника
(`admin/owner/hr/line_manager/ot_pb_lead`): выгрузка отдаёт всё разом, включая
СНИЛС/паспорт/медицину, и это ровно то действие, которое разд. 63.2 требует
держать на коротком поводке.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.privacy.service import (
    PDN_FEATURE_CODE,
    PdnAccessJournal,
    PdnSubjectExportService,
    load_subject,
    to_access_log_entry,
)
from app.schemas.privacy import PdnAccessLogPage, PdnSubjectExport
from app.services.audit import AuditService

router = APIRouter(prefix="/privacy", tags=["privacy"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_PDN_ROLES = ["admin", "owner", "hr"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


PdnAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_PDN_ROLES,
            action="access personal data of a subject",
        )
    ),
]


async def _require_feature(session: SessionDep, tenant: TenantDep) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), PDN_FEATURE_CODE, default=True)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PDN_SUBJECT_RIGHTS_DISABLED",
                message="Personal data subject rights are not enabled for this tenant",
                error_type="privacy",
            ),
        )


FeatureGate = Depends(_require_feature)


def _subject_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(
            code="PDN_SUBJECT_NOT_FOUND",
            message="Personal data subject not found",
            error_type="privacy",
        ),
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _actor_role(access: AccessContext) -> str | None:
    role = getattr(access.user, "role", None)
    return getattr(role, "value", None) or (str(role) if role else None)


@router.get(
    "/subjects/{person_id}/export",
    response_model=PdnSubjectExport,
    dependencies=[FeatureGate],
    summary="Выгрузка всех персональных данных субъекта (152-ФЗ, право на доступ)",
)
async def export_subject_data(
    person_id: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
    purpose: Annotated[
        str | None,
        Query(max_length=255, description="Цель/основание запроса — попадает в журнал доступа"),
    ] = None,
) -> PdnSubjectExport:
    TenantContextValidator.ensure_tenant_context(tenant)

    service = PdnSubjectExportService(tenant_id=str(tenant.id), session=session)
    export = await service.build(person_id)
    if export is None:
        raise _subject_not_found()

    # Журналируем ДО отдачи ответа и в той же транзакции: выгрузка без следа в
    # журнале — нарушение разд. 66.2, поэтому «отдали, но не записали» невозможно.
    journal = PdnAccessJournal(session)
    await journal.record(
        tenant_id=str(tenant.id),
        subject_person_id=person_id,
        action="export",
        actor_user_id=str(access.user.id) if access.user else None,
        actor_email=getattr(access.user, "email", None),
        actor_role=_actor_role(access),
        purpose=purpose,
        ip=_client_ip(request),
        request_id=request.headers.get("x-request-id"),
    )
    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="pdn.subject_export",
        object_type="person",
        object_id=person_id,
        user_id=str(access.user.id) if access.user else None,
        ip=_client_ip(request),
        details={"purpose": purpose, "categories": export.data_categories},
    )
    await session.commit()
    return export


@router.get(
    "/subjects/{person_id}/access-log",
    response_model=PdnAccessLogPage,
    dependencies=[FeatureGate],
    summary="Журнал доступа к персональным данным субъекта (152-ФЗ)",
)
async def read_subject_access_log(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PdnAccessLogPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    if await load_subject(session, tenant_id=str(tenant.id), person_id=person_id) is None:
        raise _subject_not_found()

    journal = PdnAccessJournal(session)
    rows, total = await journal.list_for_subject(
        tenant_id=str(tenant.id),
        subject_person_id=person_id,
        limit=limit,
        offset=offset,
    )
    return PdnAccessLogPage(
        items=[to_access_log_entry(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
