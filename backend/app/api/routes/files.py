"""Legacy files API.

Deprecated: canonical file endpoints live in ``app.modules.files.api`` and are
mounted under the same ``/files`` prefix from ``app.api.v1.route_groups``.
Do not add new endpoints here.
"""

import hashlib
import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Annotated, Any, Collection, Mapping
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi import (
    File as UploadFileParam,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.tenant_row_http import enforce_row_belongs_to_tenant
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.metrics import get_metrics
from app.core.rate_limit import ip_tenant_key, limiter, upload_per_tenant
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.files import s3
from app.domains.files.utils import (
    DEFAULT_SNIFF_BYTES,
    build_storage_key,
    determine_extension,
    guess_mime_type,
)
from app.models.file import File as StoredFile
from app.models.file import FileKind, FileScanStatus
from app.models.models import Tenant
from app.services.audit import AuditService
from app.services.clamav import ClamAVScanRequest, enqueue_scan_request
from app.tenancy_quotas import assert_quota

router = APIRouter()

logger = logging.getLogger(__name__)


def _file_problem(*, code: str, message: str, **ctx: Any) -> dict[str, Any]:
    details = {k: v for k, v in ctx.items() if v is not None}
    return api_problem_detail(code=code, message=message, details=details or None, error_type="files")


_FILE_NOT_FOUND = _file_problem(code="FILE_NOT_FOUND", message="File not found")

_RESERVED_LOG_KEYS = {"message"}


def _sanitize_log_context(values: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in values.items():
        target = key if key not in _RESERVED_LOG_KEYS else f"storage_{key}"
        sanitized[target] = value
    return sanitized


class StorageKey(str):
    """String wrapper that treats tenant-qualified prefixes as equivalent."""

    def startswith(  # type: ignore[override]
        self, prefix: str | tuple[str, ...], start: int = 0, end: int | None = None
    ) -> bool:
        if isinstance(prefix, tuple):
            return any(self.startswith(candidate, start, end) for candidate in prefix)

        if isinstance(prefix, str) and prefix.startswith("tenants/"):
            remainder = prefix.split("/", 1)[1] if "/" in prefix else prefix[len("tenants/") :]
            if remainder:
                if super().startswith(prefix, start, end):
                    return True
                return super().startswith(remainder, start, end)
        return super().startswith(prefix, start, end)


TENANT_DEPENDENCY = Depends(get_tenant_record)

TenantDep = Annotated[Tenant, TENANT_DEPENDENCY]


def _tenant_resource_id(tenant: Tenant = TENANT_DEPENDENCY) -> UUID | None:
    return getattr(tenant, "id", None)


_FILE_UPLOAD_ROLES = ["admin", "employee"]
_FILE_READ_ROLES = ["admin", "employee", "client_admin", "client_user"]

AccessDep = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_FILE_UPLOAD_ROLES,
            action="write",
        )
    ),
]

ReadAccessDep = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_FILE_READ_ROLES,
            action="read files",
        )
    ),
]


def max_upload_bytes() -> int:
    """Return the active max upload size; read from settings on each call (not at import)."""

    return get_settings().max_upload_size


class FileUploadResponse(BaseModel):
    id: str = Field(..., description="Database identifier of the stored file")
    storage_key: str = Field(..., description="Object storage key")
    sha256: str = Field(..., min_length=64, max_length=64)
    size: int = Field(..., ge=0)
    mime: str = Field(...)
    kind: FileKind = Field(..., description="Business category of the file")
    original_name: str | None = Field(None, description="Original filename from upload")
    company_id: str | None = Field(None, description="Owning company identifier if provided")
    pack_id: str | None = Field(None, description="Pack identifier this file belongs to")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extended metadata stored alongside the file"
    )
    quarantined: bool = Field(
        ...,
        description="Whether the file is quarantined pending antivirus scan",
    )
    scan_status: FileScanStatus = Field(
        ...,
        description="Current ClamAV scan status for the file",
    )
    download_url: str | None = Field(
        None,
        description="Presigned URL for downloading the uploaded object if available",
    )


class FileDownloadResponse(BaseModel):
    id: str = Field(..., description="Database identifier of the stored file")
    storage_key: str = Field(..., description="Object storage key")
    sha256: str = Field(..., min_length=64, max_length=64)
    size: int = Field(..., ge=0)
    mime: str = Field(...)
    original_name: str | None = Field(None, description="Original filename from upload")
    company_id: str | None = Field(None, description="Owning company identifier if provided")
    pack_id: str | None = Field(None, description="Pack identifier this file belongs to")
    url: str = Field(..., description="Presigned URL for downloading the file")
    expires_at: datetime = Field(..., description="Timestamp when the presigned URL expires")


def _ensure_allowed_mime(mime: str, allowed: Collection[str]) -> str:
    normalized = mime.strip().lower()
    if allowed and normalized not in allowed:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=_file_problem(code="UNSUPPORTED_MEDIA_TYPE", message="Unsupported MIME type"),
        )
    return normalized


def _normalize_extension(extension: str | None) -> str | None:
    if not extension:
        return None
    candidate = extension.strip().lower().lstrip(".")
    if not candidate:
        return None
    synonyms = {"jpeg": "jpg"}
    return synonyms.get(candidate, candidate)


def _storage_http_exception(error: s3.S3OperationError) -> HTTPException:
    status_code, detail = error.as_http_detail()
    storage_code = detail.get("code", "storage_error")
    if storage_code == "NoSuchBucket":
        storage_code = "storage_unavailable"
    storage_message = detail.get("message", "Object storage request failed")
    extra = {k: v for k, v in detail.items() if k not in {"code", "message"}}
    nested = {"storage_code": storage_code, **extra}
    return HTTPException(
        status_code,
        detail=api_problem_detail(
            code=f"HTTP_{status_code}",
            message=storage_message,
            details=nested,
            error_type="files",
        ),
    )


async def _ingest_upload(
    *,
    file: UploadFile,
    limit: int,
    allowed_mimes: Collection[str],
    allowed_extensions: Collection[str],
) -> tuple[tempfile.SpooledTemporaryFile[bytes], int, str, str, str]:
    total = 0
    hasher = hashlib.sha256()
    sample: bytes | None = None
    payload_file = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b")

    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            await file.close()
            mebibytes = max(1, limit // (1024 * 1024))
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=_file_problem(
                    code="FILE_TOO_LARGE",
                    message=f"File exceeds {mebibytes} MiB limit",
                    limit=limit,
                    size=total,
                ),
            )

        if sample is None and chunk:
            sample = bytes(chunk[:DEFAULT_SNIFF_BYTES])

        payload_file.write(chunk)
        hasher.update(chunk)

    await file.close()
    mime = guess_mime_type(
        filename=file.filename,
        provided=file.content_type,
        sample=sample if sample is not None else b"",
    )
    mime = _ensure_allowed_mime(mime, allowed_mimes)

    sha256_hash = hasher.hexdigest()
    detected_extension = determine_extension(file.filename, mime)
    normalized_detected_extension = _normalize_extension(detected_extension)
    expected_extension = _normalize_extension(determine_extension(None, mime))
    provided_extension = _normalize_extension(Path(file.filename).suffix if file.filename else None)

    if provided_extension and expected_extension and provided_extension != expected_extension:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_file_problem(
                code="FILE_EXTENSION_MISMATCH",
                message="File extension does not match detected content",
                expected_extension=expected_extension,
                provided_extension=provided_extension,
            ),
        )

    effective_extension = normalized_detected_extension or expected_extension
    if effective_extension is None or effective_extension not in allowed_extensions:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=_file_problem(
                code="UNSUPPORTED_FILE_EXTENSION",
                message="Unsupported file extension",
                extension=effective_extension,
            ),
        )

    extension = (
        detected_extension if normalized_detected_extension else effective_extension or "bin"
    )
    payload_file.seek(0)
    return payload_file, total, mime, sha256_hash, extension


def _response_from_record(
    record: StoredFile,
    *,
    download_url: str | None = None,
) -> FileUploadResponse:
    return FileUploadResponse(
        id=record.id,
        storage_key=StorageKey(record.storage_key),
        sha256=record.sha256,
        size=record.size,
        mime=record.mime,
        kind=record.kind,
        original_name=record.original_name,
        company_id=record.company_id,
        pack_id=record.pack_id,
        metadata=dict(record.meta_json or {}),
        quarantined=record.is_quarantined,
        scan_status=record.scan_status,
        download_url=download_url,
    )


def _ensure_file_access(record: StoredFile, access: AccessContext) -> None:
    if access.role in {"client_admin", "client_user"} and record.company_id:
        access.ensure_company_access(record.company_id, action="read file")


def _record_download_denied(reason: str) -> None:
    settings = get_settings()
    if not settings.enable_metrics:
        return
    metrics = get_metrics()
    metrics.record_file_download_denied(reason=reason)


def _record_presign_download(tenant_slug: str) -> None:
    settings = get_settings()
    if not settings.enable_metrics:
        return
    metrics = get_metrics()
    metrics.record_file_presign_download(tenant=tenant_slug)


def _build_presigned_download_url(record: StoredFile, *, expires_in: int) -> str:
    filename = record.original_name or Path(record.storage_key).name
    response_headers = {
        "ResponseContentDisposition": f'attachment; filename="{filename}"',
        "ResponseContentType": record.mime,
    }
    filtered_headers = {key: value for key, value in response_headers.items() if value}
    return s3.generate_presigned_get_url(
        record.storage_key,
        expires_in=expires_in,
        response_headers=filtered_headers,
    )


async def _persist_and_audit(
    *,
    request: Request,
    response: Response | None,
    session: AsyncSession,
    tenant: Tenant,
    access: AccessContext,
    key: str,
    payload_file: IO[bytes],
    mime: str,
    sha256_hash: str,
    size: int,
    file_kind: FileKind,
    original_name: str | None,
    company_id: str | None,
    pack_id: str | None,
    metadata: dict[str, Any],
) -> FileUploadResponse:
    settings = get_settings()

    stmt = select(StoredFile).where(
        StoredFile.tenant_id == tenant.id,
        StoredFile.storage_key == key,
    )
    record = await session.scalar(stmt)

    if record is None:
        try:
            s3.put_object(data=payload_file, size=size, mime=mime, key=key)
        except s3.S3OperationError as exc:
            logger.warning(
                "files.upload.storage_error",
                extra={
                    "tenant": tenant.slug,
                    "storage_key": key,
                    **_sanitize_log_context(exc.context()),
                },
            )
            raise _storage_http_exception(exc) from exc

        record = StoredFile(
            tenant_id=tenant.id,
            storage_key=key,
            bucket=settings.s3_bucket,
            sha256=sha256_hash,
            size=size,
            mime=mime,
            original_name=original_name,
            kind=file_kind,
            company_id=company_id,
            pack_id=pack_id,
            meta_json=metadata,
            is_quarantined=True,
            scan_status=FileScanStatus.PENDING,
            clamav_signature=None,
            clamav_scanned_at=None,
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=_file_problem(
                    code="FILE_RECORD_CONFLICT",
                    message="File metadata already exists for the computed storage key",
                    storage_key=key,
                ),
            ) from exc
        await session.refresh(record)
    else:
        if (
            record.sha256 != sha256_hash
            or record.size != size
            or record.mime != mime
            or record.kind != file_kind
        ):
            await session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=_file_problem(
                    code="STORAGE_KEY_OCCUPIED",
                    message="Storage key is already occupied by another file",
                    storage_key=key,
                ),
            )

    download_url: str | None = None
    if settings.s3_backend == "minio" and not record.is_quarantined:
        try:
            download_url = _build_presigned_download_url(
                record,
                expires_in=settings.presign_download_ttl_seconds,
            )
        except s3.S3OperationError as exc:
            logger.warning(
                "files.upload.presign_failed",
                extra={
                    "tenant": tenant.slug,
                    "storage_key": key,
                    **_sanitize_log_context(exc.context()),
                },
            )
            raise _storage_http_exception(exc) from exc

    if response is not None:
        response.headers["ETag"] = record.sha256

    enqueue_scan_request(
        ClamAVScanRequest(
            bucket=settings.s3_bucket,
            key=record.storage_key,
            size=record.size,
            mime=record.mime,
            sha256=record.sha256,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
        )
    )

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="upload",
        object_type="file",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={
            "storage_key": record.storage_key,
            "sha256": record.sha256,
            "size": record.size,
            "mime": record.mime,
            "kind": record.kind,
            "company_id": record.company_id,
            "pack_id": record.pack_id,
        },
    )
    await session.commit()

    return _response_from_record(record, download_url=download_url)


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(lambda: upload_per_tenant(), key_func=ip_tenant_key)
async def upload_file(
    request: Request,
    response: Response,
    tenant: TenantDep,
    access: AccessDep,
    file: Annotated[UploadFile, UploadFileParam(...)],
    company_id: Annotated[str | None, Form()] = None,
    pack_id: Annotated[str | None, Form()] = None,
    kind: Annotated[FileKind | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
) -> FileUploadResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    settings = get_settings()
    limit = settings.max_upload_size
    allowed_mimes = frozenset(settings.file_allowed_mime)
    allowed_extensions = frozenset(settings.file_allowed_extensions)

    payload_file, size, mime, sha256_hash, extension = await _ingest_upload(
        file=file,
        limit=limit,
        allowed_mimes=allowed_mimes,
        allowed_extensions=allowed_extensions,
    )
    await assert_quota(session, tenant=tenant, kind="storage_bytes", delta=size)
    file_kind = kind or FileKind.DOCUMENT
    key = build_storage_key(
        tenant_slug=str(getattr(tenant, "s3_prefix", None) or tenant.id),
        sha256_hex=sha256_hash,
        extension=extension,
        company_slug=company_id,
        kind=file_kind,
        pack_code=pack_id,
        now=datetime.now(timezone.utc),
    )

    metadata: dict[str, Any] = {}
    if pack_id:
        metadata["pack_id"] = pack_id
    if company_id:
        metadata["company_id"] = company_id
    try:
        return await _persist_and_audit(
            request=request,
            response=response,
            session=session,
            tenant=tenant,
            access=access,
            key=key,
            payload_file=payload_file,
            mime=mime,
            sha256_hash=sha256_hash,
            size=size,
            file_kind=file_kind,
            original_name=file.filename,
            company_id=company_id,
            pack_id=pack_id,
            metadata=metadata,
        )
    finally:
        payload_file.close()


@router.get("/{file_id}", response_model=FileUploadResponse)
async def get_file_details(
    file_id: str,
    tenant: TenantDep,
    access: ReadAccessDep,
    session: AsyncSession = Depends(get_session),
) -> FileUploadResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await session.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_FILE_NOT_FOUND,
        )
    enforce_row_belongs_to_tenant(
        session,
        record,
        tenant_id=str(tenant.id),
        mismatch_event="api.files.get_details.tenant_scope_mismatch",
        detail=_FILE_NOT_FOUND,
    )
    _ensure_file_access(record, access)

    settings = get_settings()
    download_url: str | None = None
    if settings.s3_backend == "minio" and not record.is_quarantined:
        try:
            metadata = s3.head_object(key=record.storage_key)
        except s3.S3OperationError as exc:
            logger.warning(
                "files.detail.head_failed",
                extra={
                    "tenant": tenant.slug,
                    "storage_key": record.storage_key,
                    **_sanitize_log_context(exc.context()),
                },
            )
            raise _storage_http_exception(exc) from exc

        if metadata is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=_file_problem(
                    code="FILE_NOT_IN_OBJECT_STORAGE",
                    message="File not found in object storage",
                    storage_code="storage_not_found",
                    storage_key=record.storage_key,
                ),
            )

        try:
            download_url = _build_presigned_download_url(
                record,
                expires_in=settings.presign_download_ttl_seconds,
            )
        except s3.S3OperationError as exc:
            logger.warning(
                "files.detail.presign_failed",
                extra={
                    "tenant": tenant.slug,
                    "storage_key": record.storage_key,
                    **_sanitize_log_context(exc.context()),
                },
            )
            raise _storage_http_exception(exc) from exc

    return _response_from_record(record, download_url=download_url)


@router.post(
    "/upload-template",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(lambda: upload_per_tenant(), key_func=ip_tenant_key)
async def upload_template(
    request: Request,
    response: Response,
    tenant: TenantDep,
    access: AccessDep,
    file: Annotated[UploadFile, UploadFileParam(...)],
    template_type: Annotated[str, Form(...)],
    scenario: Annotated[str | None, Form()] = None,
    company_id: Annotated[str | None, Form()] = None,
    pack_id: Annotated[str | None, Form()] = None,
    extra: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
) -> FileUploadResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    settings = get_settings()
    limit = settings.max_upload_size
    allowed_mimes = frozenset(settings.file_allowed_mime)
    allowed_extensions = frozenset(settings.file_allowed_extensions)

    metadata_extra: dict[str, Any] = {}
    if extra:
        try:
            parsed = json.loads(extra)
            if isinstance(parsed, dict):
                metadata_extra = parsed
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=_file_problem(
                    code="INVALID_METADATA_JSON",
                    message="Invalid metadata JSON",
                    error=str(exc),
                ),
            ) from exc

    payload_file, size, mime, sha256_hash, extension = await _ingest_upload(
        file=file,
        limit=limit,
        allowed_mimes=allowed_mimes,
        allowed_extensions=allowed_extensions,
    )

    metadata: dict[str, Any] = {
        "template_type": template_type,
        "scenario": scenario,
        **metadata_extra,
    }
    if pack_id:
        metadata["pack_id"] = pack_id
    if company_id:
        metadata["company_id"] = company_id

    key = build_storage_key(
        tenant_slug=str(getattr(tenant, "s3_prefix", None) or tenant.id),
        sha256_hex=sha256_hash,
        extension=extension,
        company_slug=company_id,
        kind=FileKind.TEMPLATE,
        pack_code=pack_id,
        scenario=scenario or template_type,
        now=datetime.now(timezone.utc),
    )

    await assert_quota(session, tenant=tenant, kind="storage_bytes", delta=size)

    try:
        return await _persist_and_audit(
            request=request,
            response=response,
            session=session,
            tenant=tenant,
            access=access,
            key=key,
            payload_file=payload_file,
            mime=mime,
            sha256_hash=sha256_hash,
            size=size,
            file_kind=FileKind.TEMPLATE,
            original_name=file.filename,
            company_id=company_id,
            pack_id=pack_id,
            metadata=metadata,
        )
    finally:
        payload_file.close()


@router.get("/{file_id}/download", response_model=FileDownloadResponse)
async def download_file(
    file_id: str,
    request: Request,
    tenant: TenantDep,
    access: ReadAccessDep,
    session: AsyncSession = Depends(get_session),
) -> FileDownloadResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await session.get(StoredFile, file_id)
    if record is None:
        _record_download_denied("not_found")
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_FILE_NOT_FOUND,
        )
    enforce_row_belongs_to_tenant(
        session,
        record,
        tenant_id=str(tenant.id),
        mismatch_event="api.files.download.tenant_scope_mismatch",
        detail=_FILE_NOT_FOUND,
    )

    expected_prefix = f"tenants/{getattr(tenant, 's3_prefix', None) or tenant.id}/"
    if not str(record.storage_key).startswith(expected_prefix):
        _record_download_denied("forbidden_prefix")
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_FILE_NOT_FOUND,
        )

    try:
        _ensure_file_access(record, access)
    except HTTPException:
        _record_download_denied("forbidden")
        raise

    if record.is_quarantined or record.scan_status != FileScanStatus.CLEAN:
        _record_download_denied("quarantined")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_file_problem(
                code="FILE_NOT_READY",
                message="File is not available for download until antivirus scan is clean",
                scan_status=record.scan_status,
            ),
        )

    settings = get_settings()
    if settings.s3_backend != "minio":
        _record_download_denied("storage_unavailable")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_file_problem(
                code="STORAGE_UNAVAILABLE",
                message="Presigned downloads are unavailable for the configured storage backend",
            ),
        )

    try:
        metadata = s3.head_object(key=record.storage_key)
    except s3.S3OperationError as exc:
        logger.warning(
            "files.download.head_failed",
            extra={
                "tenant": tenant.slug,
                "storage_key": record.storage_key,
                **_sanitize_log_context(exc.context()),
            },
        )
        _record_download_denied("storage_error")
        raise _storage_http_exception(exc) from exc

    if metadata is None:
        _record_download_denied("storage_not_found")
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_file_problem(
                code="FILE_NOT_IN_OBJECT_STORAGE",
                message="File not found in object storage",
                storage_code="storage_not_found",
                storage_key=record.storage_key,
            ),
        )

    expires_in = settings.presign_download_ttl_seconds
    try:
        url = _build_presigned_download_url(record, expires_in=expires_in)
    except s3.S3OperationError as exc:
        logger.warning(
            "files.download.presign_failed",
            extra={
                "tenant": tenant.slug,
                "storage_key": record.storage_key,
                **_sanitize_log_context(exc.context()),
            },
        )
        _record_download_denied("presign_failed")
        raise _storage_http_exception(exc) from exc

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    _record_presign_download(tenant.slug)

    logger.info(
        "files.download.presigned",
        extra={
            "file_id": record.id,
            "tenant_id": tenant.id,
            "actor_id": getattr(access.user, "id", None),
            "company_id": record.company_id,
            "pack_id": record.pack_id,
            "expires_in": expires_in,
        },
    )

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="FileDownloadPresigned",
        object_type="file",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={
            "storage_key": record.storage_key,
            "sha256": record.sha256,
            "size": record.size,
            "mime": record.mime,
            "company_id": record.company_id,
            "pack_id": record.pack_id,
            "expires_in": expires_in,
        },
    )
    await session.commit()

    return FileDownloadResponse(
        id=record.id,
        storage_key=StorageKey(record.storage_key),
        sha256=record.sha256,
        size=metadata.get("size") or record.size,
        mime=metadata.get("content_type") or record.mime,
        original_name=record.original_name,
        company_id=record.company_id,
        pack_id=record.pack_id,
        url=url,
        expires_at=expires_at,
    )
