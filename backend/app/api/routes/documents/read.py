"""Documents API — read / query / quality / mapping endpoints (ARCH-4 slice 5 split)."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import (
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_file_storage_service
from app.api.dependencies_managed_client import ClientScopeDep
from app.api.helpers.client_scope import apply_company_scope
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.api.routes.documents._common import (
    DocumentMappingValidateRequest,
    DocumentQualityCheckRequest,
    ReadAccessDep,
    SessionDep,
    TenantDep,
    _documents_not_found,
    router,
)
from app.core.errors import api_problem_detail
from app.core.security import AccessContext
from app.models.document import (
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
)
from app.models.file import File
from app.models.models import (
    Company,
    Template,
    Tenant,
)
from app.schemas.document import (
    DocumentCompanySummaryRead,
    DocumentDependencyMapRead,
    DocumentDependencyNpaBindingRead,
    DocumentFileLinkRead,
    DocumentHistoryEntryRead,
    DocumentPaginationRead,
    DocumentPipelineStageRead,
    DocumentReadinessRead,
    DocumentUiListResponse,
    DocumentUiRead,
    DocumentVersionCompareRead,
    DocumentVersionDataDiffRead,
)
from app.schemas.document_quality import QualityReport
from app.services.document_insights import (
    build_document_dependency_map,
    diff_version_data_json,
    load_document_versions_for_compare,
)
from app.services.document_quality import build_quality_report
from app.services.document_readiness import compute_document_readiness
from app.services.file_storage import FileStorageService

logger = logging.getLogger(__name__)


def _map_document_status(document: Document) -> str:
    # Состояния «генерируется» у строки документа НЕ БЫВАЕТ: живая генерация
    # (PipelineRun, app.tasks.document_jobs) создаёт Document только по
    # завершении, уже как GENERATED, а упавший прогон строки не создаёт вовсе.
    # Прежняя ветка читала DocumentGenerationJob — таблицу, в которую никто не
    # пишет, — и не срабатывала никогда (срез-139). Ход генерации виден в
    # контуре заданий, а не в списке документов.
    if document.status in {
        DocumentStatus.GENERATED,
        DocumentStatus.APPROVED,
        DocumentStatus.SIGNED,
        DocumentStatus.ARCHIVED,
    }:
        return "ready"
    if document.status == DocumentStatus.REVOKED:
        return "error"
    return "draft"


def _document_matches_frontend_status(document: Document, status_value: str | None) -> bool:
    if not status_value:
        return True
    return _map_document_status(document) == status_value


def _build_file_link(
    *,
    file_record: File | None,
    document_id: str,
    download_path: str,
    storage_key: str | None = None,
    created_at: datetime | None = None,
) -> DocumentFileLinkRead | None:
    if file_record is None and not storage_key:
        return None
    name = None
    if file_record is not None:
        name = file_record.original_name
    elif storage_key:
        name = storage_key.rsplit("/", 1)[-1]
    return DocumentFileLinkRead(
        id=file_record.id if file_record is not None else f"document:{document_id}",
        url=download_path,
        name=name or f"document-{document_id}",
        mime_type=file_record.mime if file_record is not None else "application/octet-stream",
        size=file_record.size if file_record is not None else 0,
        created_at=(
            file_record.created_at
            if file_record is not None
            else (created_at or datetime.now(timezone.utc))
        ),
    )


def _resolve_latest_version(document: Document) -> DocumentVersion | None:
    if not document.versions:
        return None
    return max(document.versions, key=lambda version: (version.version_number, version.created_at))


def _build_document_history(document: Document) -> list[DocumentHistoryEntryRead]:
    history: list[DocumentHistoryEntryRead] = []
    for version in sorted(
        document.versions, key=lambda item: (item.version_number, item.created_at), reverse=True
    ):
        history.append(
            DocumentHistoryEntryRead(
                id=version.id,
                created_at=version.created_at,
                updated_at=version.updated_at,
                document_id=version.document_id,
                status=(
                    version.status.value
                    if isinstance(version.status, DocumentVersionStatus)
                    else str(version.status)
                ),
                storage=_build_file_link(
                    file_record=version.file,
                    document_id=document.id,
                    download_path=f"/api/v1/documents/{document.id}/download",
                    storage_key=version.file_key,
                    created_at=version.created_at,
                ),
            )
        )
    return history


def _build_document_ui_read(document: Document) -> DocumentUiRead:
    latest_version = _resolve_latest_version(document)
    current_file = document.file or (latest_version.file if latest_version else None)
    company = document.company
    if company is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=api_problem_detail(
                code="INTERNAL_ERROR",
                message="Document data is inconsistent (company is missing)",
                error_type="server",
            ),
        )
    template_name = (
        document.template.name if document.template else None
    ) or f"Document {document.id[:8]}"
    template_type = (
        (document.template.domain if document.template else None)
        or (document.template.code if document.template else None)
        or "document"
    )
    return DocumentUiRead(
        id=document.id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        name=template_name,
        type=template_type,
        company=DocumentCompanySummaryRead(
            id=company.id,
            created_at=company.created_at,
            updated_at=company.updated_at,
            name=company.name,
            inn=company.inn or "",
            status="active",
        ),
        status=_map_document_status(document),
        version=str(latest_version.version_number if latest_version else 1),
        current_version_id=latest_version.id if latest_version else None,
        template_id=document.template_id,
        storage=_build_file_link(
            file_record=current_file,
            document_id=document.id,
            download_path=f"/api/v1/documents/{document.id}/download",
            storage_key=document.storage_key
            or (latest_version.file_key if latest_version else None),
            created_at=document.updated_at,
        ),
        history=_build_document_history(document),
    )


def _document_read_query(tenant_id: str):
    return (
        select(Document)
        .where(Document.tenant_id == tenant_id)
        .options(
            selectinload(Document.company),
            selectinload(Document.template),
            selectinload(Document.template_version),
            selectinload(Document.file),
            selectinload(Document.versions).selectinload(DocumentVersion.file),
        )
    )


@router.get("", response_model=DocumentUiListResponse)
async def list_documents(
    request: Request,
    response: Response,
    scope: ClientScopeDep,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
    search: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    company_id: str | None = Query(default=None),
    template_id: str | None = Query(default=None),
    created_by: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    type_value: str | None = Query(default=None, alias="type"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
) -> DocumentUiListResponse | Response:
    access.ensure_tenant_access(tenant.id, action="read documents")

    stmt = _document_read_query(str(tenant.id))
    # Работа «от имени клиента» (BIZ-49 срез-11): у документа своя организация,
    # поэтому фильтр прямой. Ставим ПЕРЕД остальными условиями — так его не
    # обойти параметром ?company_id=<чужая организация>: сужение остаётся
    # сужением, что бы ни просил вызывающий.
    stmt = apply_company_scope(stmt, Document.company_id, scope)
    if company_id:
        stmt = stmt.where(Document.company_id == company_id)
    if template_id:
        stmt = stmt.where(Document.template_id == template_id)
    if created_by:
        stmt = stmt.where(Document.created_by == created_by)
    if created_from:
        stmt = stmt.where(Document.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Document.created_at <= created_to)

    scoped_company_ids = access.claims.get("company_ids")
    if isinstance(scoped_company_ids, list) and scoped_company_ids:
        stmt = stmt.where(Document.company_id.in_([str(value) for value in scoped_company_ids]))
    elif access.company_id:
        stmt = stmt.where(Document.company_id == str(access.company_id))

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Document.id.ilike(pattern),
                Document.company.has(Company.name.ilike(pattern)),
                Document.template.has(
                    or_(Template.name.ilike(pattern), Template.code.ilike(pattern))
                ),
            )
        )
    if type_value:
        stmt = stmt.where(
            Document.template.has(or_(Template.domain == type_value, Template.code == type_value))
        )
    if status_value == "generating":
        # См. _map_document_status: такого состояния у документа нет. Список
        # честно пуст, а не «все документы» (как было бы для неизвестного
        # значения) и не 200 с выдумкой из мёртвой таблицы.
        stmt = stmt.where(false())
    elif status_value == "ready":
        stmt = stmt.where(
            Document.status.in_(
                [
                    DocumentStatus.GENERATED,
                    DocumentStatus.APPROVED,
                    DocumentStatus.SIGNED,
                    DocumentStatus.ARCHIVED,
                ]
            )
        )
    elif status_value == "draft":
        stmt = stmt.where(Document.status.in_([DocumentStatus.DRAFT, DocumentStatus.REVIEW]))
    elif status_value == "error":
        stmt = stmt.where(Document.status == DocumentStatus.REVOKED)

    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        (
            await session.execute(
                stmt.order_by(Document.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    items: list[DocumentUiRead] = []
    for document in rows:
        access.ensure_abac(
            action="read document",
            company_id=document.company_id,
            document_id=document.id,
            document_status=(
                document.status.value if hasattr(document.status, "value") else str(document.status)
            ),
            document_owner_id=document.created_by,
            site_id=document.site_id,
            site_company_id=document.company_id,
        )
        items.append(_build_document_ui_read(document))

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("page", page),
            ("page_size", page_size),
            ("total", total),
            # Иначе кэш, набранный вне контекста, вернулся бы 304-м ответом
            # уже внутри контекста клиента.
            ("managed_client", scope.client_id if scope else ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )

    return DocumentUiListResponse(
        items=items,
        pagination=DocumentPaginationRead(page=page, page_size=page_size, total=total),
    )


@router.get("/{document_id}", response_model=DocumentUiRead)
async def get_document(
    document_id: str,
    scope: ClientScopeDep,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
) -> DocumentUiRead:
    access.ensure_tenant_access(tenant.id, action="read document")
    document = (
        await session.execute(
            _document_read_query(str(tenant.id)).where(Document.id == document_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    # Чужой документ — «не найден», а не «запрещено»: иначе перебором
    # идентификаторов виден состав дел других клиентов аутсорсера.
    if scope is not None and (
        not scope.visible or str(document.company_id) != str(scope.company_id)
    ):
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    access.ensure_abac(
        action="read document",
        company_id=document.company_id,
        document_id=document.id,
        document_status=(
            document.status.value if hasattr(document.status, "value") else str(document.status)
        ),
        document_owner_id=document.created_by,
        site_id=document.site_id,
        site_company_id=document.company_id,
    )
    return _build_document_ui_read(document)


@router.get("/{document_id}/readiness", response_model=DocumentReadinessRead)
async def get_document_readiness_endpoint(
    document_id: str,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
) -> DocumentReadinessRead:
    access.ensure_tenant_access(tenant.id, action="read document")
    document = (
        await session.execute(
            _document_read_query(str(tenant.id)).where(Document.id == document_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    access.ensure_abac(
        action="read document",
        company_id=document.company_id,
        document_id=document.id,
        document_status=(
            document.status.value if hasattr(document.status, "value") else str(document.status)
        ),
        document_owner_id=document.created_by,
        site_id=document.site_id,
        site_company_id=document.company_id,
    )
    snap = compute_document_readiness(document)
    return DocumentReadinessRead(
        score=snap.score,
        blockers=snap.blockers,
        recommended_actions=snap.recommended_actions,
        pipeline_stages=[
            DocumentPipelineStageRead(
                stage_id=s.stage_id,
                label=s.label,
                complete=s.complete,
                detail=s.detail,
            )
            for s in snap.pipeline_stages
        ],
    )


@router.post("/quality:check", response_model=QualityReport)
async def check_document_quality(payload: DocumentQualityCheckRequest) -> QualityReport:
    report = build_quality_report(
        data=payload.data,
        required_fields=payload.required_fields,
        date_fields=payload.date_fields,
        numeric_fields=payload.numeric_fields,
        rendered_text=payload.rendered_text,
    )
    return report


@router.post("/mapping:validate")
async def validate_document_mapping(payload: DocumentMappingValidateRequest) -> dict[str, Any]:
    mapping_values = {
        str(value).strip() for value in payload.mapping.values() if str(value).strip()
    }
    missing_required = sorted(
        field
        for field in payload.required_template_fields
        if str(field).strip() and str(field).strip() not in mapping_values
    )
    unmapped_source = sorted(
        source
        for source in payload.source_fields
        if str(source).strip() and not str(payload.mapping.get(source, "")).strip()
    )
    return {
        "ok": len(missing_required) == 0,
        "missing_required_fields": missing_required,
        "unmapped_source_fields": unmapped_source,
        "summary": {
            "source_total": len(payload.source_fields),
            "mapped_total": len(mapping_values),
            "missing_required_total": len(missing_required),
            "unmapped_source_total": len(unmapped_source),
        },
    }


@router.get("/{document_id}/versions/compare", response_model=DocumentVersionCompareRead)
async def compare_document_versions_endpoint(
    document_id: str,
    left_version_id: str = Query(...),
    right_version_id: str = Query(...),
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
) -> DocumentVersionCompareRead:
    access.ensure_tenant_access(tenant.id, action="read document")
    document = (
        await session.execute(
            _document_read_query(str(tenant.id)).where(Document.id == document_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    access.ensure_abac(
        action="read document",
        company_id=document.company_id,
        document_id=document.id,
        document_status=(
            document.status.value if hasattr(document.status, "value") else str(document.status)
        ),
        document_owner_id=document.created_by,
        site_id=document.site_id,
        site_company_id=document.company_id,
    )
    try:
        left_v, right_v = await load_document_versions_for_compare(
            session,
            tenant_id=str(tenant.id),
            document_id=document_id,
            left_version_id=left_version_id,
            right_version_id=right_version_id,
        )
    except ValueError:
        raise _documents_not_found(
            code="DOCUMENT_VERSION_NOT_FOUND", message="Version not found"
        ) from None

    left_data = dict(left_v.data_json or {})
    right_data = dict(right_v.data_json or {})
    raw_diffs = diff_version_data_json(left_data, right_data)
    return DocumentVersionCompareRead(
        document_id=document_id,
        left_version_id=left_v.id,
        right_version_id=right_v.id,
        diffs=[
            DocumentVersionDataDiffRead(
                field=d["field"],
                before=d.get("before"),
                after=d.get("after"),
                change=str(d["change"]),
            )
            for d in raw_diffs
        ],
        template_version_changed=(
            (left_v.template_version_id or "") != (right_v.template_version_id or "")
            or (left_v.template_version or "") != (right_v.template_version or "")
        ),
    )


@router.get("/{document_id}/dependency-map", response_model=DocumentDependencyMapRead)
async def get_document_dependency_map_endpoint(
    document_id: str,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
) -> DocumentDependencyMapRead:
    access.ensure_tenant_access(tenant.id, action="read document")
    document = (
        await session.execute(
            _document_read_query(str(tenant.id)).where(Document.id == document_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    access.ensure_abac(
        action="read document",
        company_id=document.company_id,
        document_id=document.id,
        document_status=(
            document.status.value if hasattr(document.status, "value") else str(document.status)
        ),
        document_owner_id=document.created_by,
        site_id=document.site_id,
        site_company_id=document.company_id,
    )
    raw = await build_document_dependency_map(session, tenant_id=str(tenant.id), document=document)
    npa = [
        DocumentDependencyNpaBindingRead(
            binding_id=b["binding_id"],
            npa_id=b["npa_id"],
            npa_code=b["npa_code"],
            npa_title=b["npa_title"],
            ref=b.get("ref"),
            entity_type=b["entity_type"],
        )
        for b in raw.get("npa_bindings") or []
    ]
    return DocumentDependencyMapRead(
        template=raw.get("template"),
        template_version=raw.get("template_version"),
        npa_bindings=npa,
        pipeline_profile_hint=raw.get("pipeline_profile_hint"),
    )


@router.get("/{document_id}/status", response_model=DocumentUiRead)
async def get_document_status(
    document_id: str,
    scope: ClientScopeDep,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
) -> DocumentUiRead:
    # Статус — та же карточка, поэтому и контекст клиента тот же: иначе
    # «запрещённый» документ виден через соседний роут.
    return await get_document(
        document_id=document_id, scope=scope, tenant=tenant, session=session, access=access
    )


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    scope: ClientScopeDep,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = ReadAccessDep,
    storage: FileStorageService = Depends(get_file_storage_service),
) -> Response:
    access.ensure_tenant_access(tenant.id, action="download document")
    document = (
        await session.execute(
            _document_read_query(str(tenant.id)).where(Document.id == document_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    # Скачивание — самый ценный способ утечки: файл уносится целиком.
    if scope is not None and (
        not scope.visible or str(document.company_id) != str(scope.company_id)
    ):
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message="Document not found")
    access.ensure_abac(
        action="download document",
        company_id=document.company_id,
        document_id=document.id,
        document_status=(
            document.status.value if hasattr(document.status, "value") else str(document.status)
        ),
        document_owner_id=document.created_by,
        site_id=document.site_id,
        site_company_id=document.company_id,
    )

    latest_version = _resolve_latest_version(document)
    current_file = document.file or (latest_version.file if latest_version else None)
    storage_key = (
        document.storage_key
        or (current_file.storage_key if current_file else None)
        or (latest_version.file_key if latest_version else None)
    )
    if not storage_key:
        raise _documents_not_found(
            code="DOCUMENT_FILE_NOT_FOUND", message="Document file not found"
        )

    try:
        payload = storage.download(storage_key)
    except KeyError as exc:
        raise _documents_not_found(
            code="DOCUMENT_FILE_NOT_FOUND", message="Document file not found"
        ) from exc

    filename = (
        current_file.original_name
        if current_file and current_file.original_name
        else f"document-{document.id}.bin"
    ).replace('"', "")
    media_type = current_file.mime if current_file else "application/octet-stream"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
