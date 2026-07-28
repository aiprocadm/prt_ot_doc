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
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.privacy.consents import (
    PdnConsentService,
    PdnErasureService,
    UnknownLegalBasisError,
    UnknownPurposeError,
)
from app.modules.privacy.registry import (
    InvalidRegistryValueError,
    PdnAgreementService,
    PdnProcessingRegistryService,
)
from app.modules.privacy.service import (
    PDN_FEATURE_CODE,
    PdnAccessJournal,
    PdnSubjectExportService,
    load_subject,
    to_access_log_entry,
)
from app.schemas.privacy import (
    PdnAccessLogPage,
    PdnAgreementCreate,
    PdnAgreementEntry,
    PdnAgreementPage,
    PdnConsentEntry,
    PdnConsentGrant,
    PdnConsentPage,
    PdnConsentWithdraw,
    PdnErasureRequest,
    PdnErasureResult,
    PdnProcessingActivityEntry,
    PdnProcessingActivityPage,
    PdnProcessingActivityUpsert,
    PdnSubjectExport,
)
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


def _bad_vocabulary(code: str, field: str, value: str) -> HTTPException:
    """Значение вне справочника разд. 66.1 — это ошибка запроса, а не 500."""

    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code=code,
            message=f"Unsupported {field}: {value}",
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


def _to_consent_entry(row) -> PdnConsentEntry:  # noqa: ANN001 - ORM row
    return PdnConsentEntry(
        id=str(row.id),
        subject_person_id=str(row.subject_person_id),
        purpose=row.purpose,
        legal_basis=row.legal_basis,
        version=row.consent_version,
        status=row.status,
        document_ref=row.document_ref,
        text_sha256=row.text_sha256,
        expires_at=row.expires_at,
        granted_at=row.granted_at,
        withdrawn_at=row.withdrawn_at,
        withdrawal_reason=row.withdrawal_reason,
        recorded_by_email=row.recorded_by_email,
    )


def _to_erasure_result(record, *, already: bool) -> PdnErasureResult:  # noqa: ANN001 - ORM row
    return PdnErasureResult(
        id=str(record.id),
        subject_person_id=str(record.subject_person_id),
        pseudonym=record.pseudonym,
        reason=record.reason,
        scrubbed_fields=dict(record.scrubbed_fields or {}),
        retained_sections=dict(record.retained_sections or {}),
        performed_at=record.performed_at,
        performed_by_email=record.performed_by_email,
        already_anonymized=already,
    )


@router.get(
    "/subjects/{person_id}/consents",
    response_model=PdnConsentPage,
    dependencies=[FeatureGate],
    summary="Согласия субъекта и действующие правовые основания обработки (152-ФЗ)",
)
async def list_subject_consents(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnConsentPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    if await load_subject(session, tenant_id=str(tenant.id), person_id=person_id) is None:
        raise _subject_not_found()

    service = PdnConsentService(session, tenant_id=str(tenant.id))
    rows = await service.list_for_subject(person_id)
    return PdnConsentPage(
        items=[_to_consent_entry(row) for row in rows],
        total=len(rows),
        remaining_legal_bases=await service.remaining_legal_bases(person_id),
    )


@router.post(
    "/subjects/{person_id}/consents",
    response_model=PdnConsentEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
    summary="Зафиксировать согласие субъекта (новая версия, 152-ФЗ разд. 66.1)",
)
@audit_operation("pdn.consent_grant", "person")
async def grant_subject_consent(
    person_id: str,
    payload: PdnConsentGrant,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnConsentEntry:
    TenantContextValidator.ensure_tenant_context(tenant)

    if await load_subject(session, tenant_id=str(tenant.id), person_id=person_id) is None:
        raise _subject_not_found()

    service = PdnConsentService(session, tenant_id=str(tenant.id))
    try:
        consent = await service.grant(
            person_id=person_id,
            purpose=payload.purpose,
            legal_basis=payload.legal_basis,
            document_ref=payload.document_ref,
            text_sha256=payload.text_sha256,
            expires_at=payload.expires_at,
            actor_user_id=str(access.user.id) if access.user else None,
            actor_email=getattr(access.user, "email", None),
        )
    except UnknownPurposeError as exc:
        raise _bad_vocabulary("PDN_UNKNOWN_PURPOSE", "purpose", str(exc)) from exc
    except UnknownLegalBasisError as exc:
        raise _bad_vocabulary("PDN_UNKNOWN_LEGAL_BASIS", "legal_basis", str(exc)) from exc

    await PdnAccessJournal(session).record(
        tenant_id=str(tenant.id),
        subject_person_id=person_id,
        action="consent_grant",
        actor_user_id=str(access.user.id) if access.user else None,
        actor_email=getattr(access.user, "email", None),
        actor_role=_actor_role(access),
        purpose=payload.purpose,
        ip=_client_ip(request),
        request_id=request.headers.get("x-request-id"),
    )
    return _to_consent_entry(consent)


@router.post(
    "/subjects/{person_id}/consents/withdraw",
    response_model=PdnConsentEntry,
    dependencies=[FeatureGate],
    summary="Отозвать согласие субъекта (152-ФЗ разд. 66.2)",
)
@audit_operation("pdn.consent_withdraw", "person")
async def withdraw_subject_consent(
    person_id: str,
    payload: PdnConsentWithdraw,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnConsentEntry:
    TenantContextValidator.ensure_tenant_context(tenant)

    if await load_subject(session, tenant_id=str(tenant.id), person_id=person_id) is None:
        raise _subject_not_found()

    service = PdnConsentService(session, tenant_id=str(tenant.id))
    consent = await service.withdraw(
        person_id=person_id, purpose=payload.purpose, reason=payload.reason
    )
    if consent is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PDN_CONSENT_NOT_FOUND",
                message="No active consent for this purpose",
                error_type="privacy",
            ),
        )

    await PdnAccessJournal(session).record(
        tenant_id=str(tenant.id),
        subject_person_id=person_id,
        action="consent_withdraw",
        actor_user_id=str(access.user.id) if access.user else None,
        actor_email=getattr(access.user, "email", None),
        actor_role=_actor_role(access),
        purpose=payload.purpose,
        ip=_client_ip(request),
        request_id=request.headers.get("x-request-id"),
    )
    return _to_consent_entry(consent)


@router.post(
    "/subjects/{person_id}/anonymize",
    response_model=PdnErasureResult,
    dependencies=[FeatureGate],
    summary="Обезличить субъекта: право на удаление (152-ФЗ разд. 66.2)",
)
@audit_operation("pdn.subject_anonymize", "person")
async def anonymize_subject(
    person_id: str,
    payload: PdnErasureRequest,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnErasureResult:
    """Необратимо вычищает прямые идентификаторы субъекта.

    Связанные записи (обучение, медосмотры, СИЗ) НЕ удаляются: их хранения
    требует закон, а после вычистки идентификаторов они уже обезличены. Что
    именно вычищено и что сохранено — в ответе и в ``pdn_erasure_record``.
    """

    TenantContextValidator.ensure_tenant_context(tenant)

    person = await load_subject(session, tenant_id=str(tenant.id), person_id=person_id)
    if person is None:
        raise _subject_not_found()

    outcome = await PdnErasureService(session, tenant_id=str(tenant.id)).anonymize(
        person,
        reason=payload.reason,
        actor_user_id=str(access.user.id) if access.user else None,
        actor_email=getattr(access.user, "email", None),
    )

    # Журналируем и повторный вызов: сам факт обращения к ПДн субъекта подлежит
    # учёту независимо от того, изменил ли он что-нибудь.
    await PdnAccessJournal(session).record(
        tenant_id=str(tenant.id),
        subject_person_id=person_id,
        action="anonymize",
        actor_user_id=str(access.user.id) if access.user else None,
        actor_email=getattr(access.user, "email", None),
        actor_role=_actor_role(access),
        purpose=payload.reason,
        ip=_client_ip(request),
        request_id=request.headers.get("x-request-id"),
    )
    return _to_erasure_result(outcome.record, already=outcome.already_anonymized)


def _to_activity_entry(row) -> PdnProcessingActivityEntry:  # noqa: ANN001 - ORM row
    return PdnProcessingActivityEntry(
        id=str(row.id),
        code=row.code,
        name=row.name,
        purpose=row.purpose,
        purpose_description=row.purpose_description,
        legal_basis=row.legal_basis,
        data_categories=list(row.data_categories or []),
        subject_categories=list(row.subject_categories or []),
        retention_months=row.retention_months,
        retention_basis=row.retention_basis,
        access_roles=list(row.access_roles or []),
        recipients=list(row.recipients or []),
        storage_location=row.storage_location,
        cross_border_transfer=row.cross_border_transfer,
        is_active=row.is_active,
        review_at=row.review_at,
        notes=row.notes,
    )


def _to_agreement_entry(row) -> PdnAgreementEntry:  # noqa: ANN001 - ORM row
    return PdnAgreementEntry(
        id=str(row.id),
        kind=row.kind,
        party_role=row.party_role,
        counterparty_name=row.counterparty_name,
        counterparty_inn=row.counterparty_inn,
        counterparty_tenant_slug=row.counterparty_tenant_slug,
        document_ref=row.document_ref,
        signed_at=row.signed_at,
        valid_until=row.valid_until,
        status=row.status,
        subprocessing_allowed=row.subprocessing_allowed,
        breach_notification_hours=row.breach_notification_hours,
        covered_activity_codes=list(row.covered_activity_codes or []),
        notes=row.notes,
    )


def _activity_page(rows) -> PdnProcessingActivityPage:  # noqa: ANN001 - ORM rows
    items = [_to_activity_entry(row) for row in rows]
    return PdnProcessingActivityPage(
        items=items,
        total=len(items),
        has_special_categories=any(
            category != "regular"
            for item in items
            if item.is_active
            for category in item.data_categories
        ),
    )


@router.get(
    "/processing-activities",
    response_model=PdnProcessingActivityPage,
    dependencies=[FeatureGate],
    summary="Реестр обработки персональных данных (152-ФЗ разд. 66.1)",
)
async def list_processing_activities(
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
    active_only: Annotated[bool, Query(description="Только действующие процессы")] = False,
) -> PdnProcessingActivityPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnProcessingRegistryService(session, tenant_id=str(tenant.id))
    return _activity_page(await service.list_activities(active_only=active_only))


@router.put(
    "/processing-activities",
    response_model=PdnProcessingActivityEntry,
    dependencies=[FeatureGate],
    summary="Создать или обновить процесс обработки ПДн (по коду)",
)
@audit_operation("pdn.activity_upsert", "pdn_processing_activity")
async def upsert_processing_activity(
    payload: PdnProcessingActivityUpsert,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnProcessingActivityEntry:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnProcessingRegistryService(session, tenant_id=str(tenant.id))
    try:
        activity = await service.upsert(**payload.model_dump())
    except InvalidRegistryValueError as exc:
        raise _bad_vocabulary("PDN_INVALID_REGISTRY_VALUE", exc.field_name, exc.value) from exc
    return _to_activity_entry(activity)


@router.post(
    "/processing-activities/seed-defaults",
    response_model=PdnProcessingActivityPage,
    dependencies=[FeatureGate],
    summary="Досеять типовой реестр обработки (не перезаписывает существующее)",
)
@audit_operation("pdn.activity_seed_defaults", "pdn_processing_activity")
async def seed_default_processing_activities(
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnProcessingActivityPage:
    """Пустая форма на 12 полей не заполняется никем — и в проверку арендатор
    приходит с пустым реестром. Типовой набор выведен из того, что платформа
    реально делает с ПДн; дальше арендатор правит его под себя."""

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnProcessingRegistryService(session, tenant_id=str(tenant.id))
    await service.seed_defaults()
    return _activity_page(await service.list_activities())


@router.delete(
    "/processing-activities/{code}",
    response_model=PdnProcessingActivityEntry,
    dependencies=[FeatureGate],
    summary="Прекратить процесс обработки (без удаления из реестра)",
)
@audit_operation("pdn.activity_deactivate", "pdn_processing_activity")
async def deactivate_processing_activity(
    code: str,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnProcessingActivityEntry:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnProcessingRegistryService(session, tenant_id=str(tenant.id))
    activity = await service.deactivate(code)
    if activity is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PDN_ACTIVITY_NOT_FOUND",
                message="Processing activity not found",
                error_type="privacy",
            ),
        )
    return _to_activity_entry(activity)


@router.get(
    "/agreements",
    response_model=PdnAgreementPage,
    dependencies=[FeatureGate],
    summary="Договоры поручения обработки и роли Оператор/Обработчик (152-ФЗ разд. 66.3)",
)
async def list_pdn_agreements(
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnAgreementPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnAgreementService(session, tenant_id=str(tenant.id))
    rows = await service.list_agreements()
    return PdnAgreementPage(
        items=[_to_agreement_entry(row) for row in rows],
        total=len(rows),
        uncovered_activity_codes=await service.uncovered_activity_codes(),
    )


@router.post(
    "/agreements",
    response_model=PdnAgreementEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
    summary="Зафиксировать договор поручения обработки ПДн",
)
@audit_operation("pdn.agreement_create", "pdn_processing_agreement")
async def create_pdn_agreement(
    payload: PdnAgreementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnAgreementEntry:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnAgreementService(session, tenant_id=str(tenant.id))
    try:
        agreement = await service.create(**payload.model_dump())
    except InvalidRegistryValueError as exc:
        raise _bad_vocabulary("PDN_INVALID_REGISTRY_VALUE", exc.field_name, exc.value) from exc
    return _to_agreement_entry(agreement)


@router.post(
    "/agreements/{agreement_id}/terminate",
    response_model=PdnAgreementEntry,
    dependencies=[FeatureGate],
    summary="Расторгнуть договор поручения (статус, без удаления)",
)
@audit_operation("pdn.agreement_terminate", "pdn_processing_agreement")
async def terminate_pdn_agreement(
    agreement_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: PdnAccess,
) -> PdnAgreementEntry:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = PdnAgreementService(session, tenant_id=str(tenant.id))
    agreement = await service.terminate(agreement_id)
    if agreement is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PDN_AGREEMENT_NOT_FOUND",
                message="Processing agreement not found",
                error_type="privacy",
            ),
        )
    return _to_agreement_entry(agreement)
