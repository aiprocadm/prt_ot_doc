"""S3/MinIO helper functions with normalized error handling."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.services.file_storage import FileStorageService as MemoryStorageService
from app.services.storage import FileStorageError
from app.services.storage import FileStorageService as LocalStorageService

logger = logging.getLogger(__name__)

__all__ = [
    "S3OperationError",
    "_resolve_endpoint",
    "ensure_bucket",
    "put_object",
    "head_object",
    "stream_object",
    "get_client",
    "reset_client_cache",
    "generate_presigned_get_url",
    "generate_presigned_put_url",
]

_LOCAL_METADATA_SUFFIX = ".meta.json"


_STATUS_OVERRIDES: Mapping[str, int] = {
    "NoSuchBucket": HTTPStatus.SERVICE_UNAVAILABLE,
    "RequestTimeout": HTTPStatus.GATEWAY_TIMEOUT,
    "SlowDown": HTTPStatus.SERVICE_UNAVAILABLE,
}


class S3OperationError(Exception):
    """Wrap a boto3 ``ClientError`` with normalized context."""

    __slots__ = (
        "operation",
        "status_code",
        "code",
        "message",
        "bucket",
        "key",
        "request_id",
    )

    def __init__(
        self,
        *,
        operation: str,
        status_code: int,
        code: str,
        message: str,
        bucket: str | None = None,
        key: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.code = code
        self.message = message
        self.bucket = bucket
        self.key = key
        self.request_id = request_id

    @classmethod
    def from_client_error(
        cls,
        operation: str,
        exc: ClientError,
        *,
        bucket: str | None = None,
        key: str | None = None,
    ) -> "S3OperationError":
        response = exc.response or {}
        error = response.get("Error", {}) or {}
        metadata = response.get("ResponseMetadata", {}) or {}
        raw_code = str(error.get("Code") or "unknown")
        status_code = int(metadata.get("HTTPStatusCode") or HTTPStatus.INTERNAL_SERVER_ERROR)
        status_code = _STATUS_OVERRIDES.get(raw_code, status_code)
        message = str(error.get("Message") or exc.__class__.__name__)
        request_id = metadata.get("RequestId") or metadata.get("RequestID")
        return cls(
            operation=operation,
            status_code=status_code,
            code=raw_code,
            message=message,
            bucket=bucket,
            key=key,
            request_id=request_id,
        )

    def context(self) -> dict[str, Any]:
        data = {
            "operation": self.operation,
            "status_code": self.status_code,
            "code": self.code,
            "message": self.message,
            "bucket": self.bucket,
            "key": self.key,
            "request_id": self.request_id,
        }
        return {k: v for k, v in data.items() if v is not None}

    def as_http_detail(self) -> tuple[int, dict[str, Any]]:
        detail = {"code": self.code, "message": self.message}
        if self.bucket:
            detail["bucket"] = self.bucket
        if self.key:
            detail["key"] = self.key
        if self.request_id:
            detail["request_id"] = self.request_id
        return self.status_code, detail


def _resolve_endpoint(endpoint: str, *, secure: bool) -> tuple[str | None, bool]:
    """Return boto3 endpoint URL and whether SSL should be used."""

    if not endpoint:
        return None, secure

    parsed = urlparse(endpoint)
    if parsed.scheme:
        return endpoint, parsed.scheme.lower() == "https"

    return endpoint, secure


def _using_local_backend() -> bool:
    return get_settings().s3_backend == "local"


def _using_memory_backend() -> bool:
    return get_settings().s3_backend == "memory"


@lru_cache(maxsize=1)
def _get_client() -> BaseClient:
    settings = get_settings()
    if settings.s3_backend != "minio":
        raise RuntimeError("S3 client is only available when S3_BACKEND is 'minio'")
    endpoint, secure = _resolve_endpoint(settings.s3_endpoint, secure=settings.s3_secure)

    logger.debug(
        "files.s3.client.init",
        extra={
            "endpoint": endpoint,
            "secure": secure,
            "bucket": settings.s3_bucket,
        },
    )

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        use_ssl=secure,
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
    )


@lru_cache(maxsize=1)
def _get_local_storage() -> LocalStorageService:
    settings = get_settings()
    storage = LocalStorageService(settings.storage_root_path)
    storage.ensure_ready()
    return storage


def _local_metadata_path(storage: LocalStorageService, key: str) -> Path:
    path = storage.resolve_path(key)
    return path.with_name(f"{path.name}{_LOCAL_METADATA_SUFFIX}")


def _write_local_metadata(storage: LocalStorageService, key: str, *, mime: str) -> None:
    metadata = {"content_type": mime}
    path = _local_metadata_path(storage, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata), encoding="utf-8")


def _read_local_metadata(storage: LocalStorageService, key: str) -> dict[str, Any]:
    path = _local_metadata_path(storage, key)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_client() -> BaseClient:
    """Expose cached S3 client."""

    return _get_client()


def reset_client_cache() -> None:
    """Clear cached S3 client and reload settings on next access."""

    _get_client.cache_clear()
    _get_local_storage.cache_clear()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def ensure_bucket() -> None:
    """Ensure the configured bucket exists."""
    settings = get_settings()
    if settings.s3_backend == "local":
        storage = _get_local_storage()
        storage.ensure_ready()
        logger.info(
            "files.local.storage.ready",
            extra={"root": str(settings.storage_root_path)},
        )
        return
    if settings.s3_backend == "memory":
        logger.info(
            "files.memory.storage.ready",
            extra={"backend": settings.s3_backend},
        )
        logger.info(
            "files.s3.bucket.skipped",
            extra={"bucket": settings.s3_bucket, "backend": settings.s3_backend},
        )
        return

    client = get_client()
    bucket = settings.s3_bucket

    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code") if exc.response else None
        if error_code in {"404", "NoSuchBucket", "NotFound"}:
            client.create_bucket(Bucket=bucket)
            logger.info("files.s3.bucket.created", extra={"bucket": bucket})
            return
        raise S3OperationError.from_client_error("head_bucket", exc, bucket=bucket) from exc


def put_object(*, data: bytes | BinaryIO, mime: str, key: str, size: int | None = None) -> str:
    """Upload object to S3 under provided key and return resulting ETag."""

    payload_size = size if size is not None else (len(data) if isinstance(data, (bytes, bytearray)) else None)

    settings = get_settings()
    if _using_memory_backend():
        storage = MemoryStorageService.default()
        if isinstance(data, (bytes, bytearray)):
            payload = bytes(data)
        else:
            payload = data.read()
            if not isinstance(payload, (bytes, bytearray)):
                raise TypeError("stream data must return bytes")
        storage.put(key, payload, content_type=mime)
        logger.info(
            "files.memory.object.stored",
            extra={"key": key, "content_type": mime, "size": len(payload)},
        )
        return ""
    if _using_local_backend():
        storage = _get_local_storage()
        try:
            stream: BinaryIO
            if isinstance(data, (bytes, bytearray)):
                stream = BytesIO(data)
            else:
                stream = data
            storage.upload(key=key, data=stream, content_type=mime)
            _write_local_metadata(storage, key, mime=mime)
        except FileStorageError as exc:
            raise S3OperationError(
                operation="put_object",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="LocalStorageError",
                message=str(exc),
                bucket=settings.s3_bucket,
                key=key,
            ) from exc
        logger.info(
            "files.local.object.stored",
            extra={"key": key, "content_type": mime, "size": payload_size},
        )
        return ""

    client = get_client()

    try:
        if isinstance(data, (bytes, bytearray)):
            response = client.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=mime,
            )
        else:
            response = client.upload_fileobj(
                Fileobj=data,
                Bucket=settings.s3_bucket,
                Key=key,
                ExtraArgs={"ContentType": mime},
            )
            response = {}
    except ClientError as exc:
        raise S3OperationError.from_client_error(
            "put_object", exc, bucket=settings.s3_bucket, key=key
        ) from exc

    etag = response.get("ETag", "")
    if isinstance(etag, str):
        etag = etag.strip('"')

    logger.info(
        "files.s3.object.stored",
        extra={
            "bucket": settings.s3_bucket,
            "key": key,
            "etag": etag,
            "content_type": mime,
            "size": payload_size,
        },
    )
    return etag


def head_object(*, key: str) -> dict[str, Any] | None:
    """Fetch object metadata if key exists."""

    settings = get_settings()
    if _using_memory_backend():
        storage = MemoryStorageService.default()
        blob = storage.head(key)
        if blob is None:
            return None
        return {
            "bucket": settings.s3_bucket,
            "key": key,
            "content_type": blob["content_type"],
            "size": blob["size"],
            "etag": "",
            "last_modified": None,
        }
    if _using_local_backend():
        storage = _get_local_storage()
        try:
            path = storage.resolve_path(key)
        except FileStorageError:
            return None
        if not path.exists():
            return None
        metadata = _read_local_metadata(storage, key)
        stat = path.stat()
        return {
            "bucket": settings.s3_bucket,
            "key": key,
            "content_type": metadata.get("content_type"),
            "size": stat.st_size,
            "etag": "",
            "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        }

    client = get_client()

    try:
        response = client.head_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code") if exc.response else None
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise S3OperationError.from_client_error(
            "head_object", exc, bucket=settings.s3_bucket, key=key
        ) from exc

    return {
        "bucket": settings.s3_bucket,
        "key": key,
        "content_type": response.get("ContentType"),
        "size": response.get("ContentLength"),
        "etag": response.get("ETag", "").strip('"'),
        "last_modified": response.get("LastModified"),
    }


@contextmanager
def stream_object(*, key: str) -> Iterator[BinaryIO]:
    """Yield a streaming body for the provided key, closing it afterwards."""

    settings = get_settings()
    if _using_memory_backend():
        storage = MemoryStorageService.default()
        if not storage.has(key):
            raise S3OperationError(
                operation="get_object",
                status_code=HTTPStatus.NOT_FOUND,
                code="NoSuchKey",
                message="Object not found",
                bucket=settings.s3_bucket,
                key=key,
            )
        stream = BytesIO(storage.get(key))
        try:
            yield stream
        finally:
            stream.close()
        return
    if _using_local_backend():
        storage = _get_local_storage()
        try:
            path = storage.resolve_path(key)
        except FileStorageError as exc:
            raise S3OperationError(
                operation="get_object",
                status_code=HTTPStatus.NOT_FOUND,
                code="NoSuchKey",
                message=str(exc),
                bucket=settings.s3_bucket,
                key=key,
            ) from exc
        if not path.exists():
            raise S3OperationError(
                operation="get_object",
                status_code=HTTPStatus.NOT_FOUND,
                code="NoSuchKey",
                message="Object not found",
                bucket=settings.s3_bucket,
                key=key,
            )
        stream = path.open("rb")
        try:
            yield stream
        finally:
            stream.close()
        return

    client = get_client()

    try:
        response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        raise S3OperationError.from_client_error(
            "get_object", exc, bucket=settings.s3_bucket, key=key
        ) from exc

    body = response.get("Body")
    if body is None:
        raise S3OperationError(
            operation="get_object",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="NoBody",
            message="S3 response missing body",
            bucket=settings.s3_bucket,
            key=key,
        )

    try:
        yield body
    finally:
        try:
            body.close()
        except Exception:  # pragma: no cover - best effort cleanup
            logger.debug(
                "files.s3.stream.close_failed",
                exc_info=True,
                extra={"bucket": settings.s3_bucket, "key": key},
            )




def generate_presigned_put_url(
    key: str,
    *,
    bucket: str | None = None,
    expires_in: int = 3600,
    content_type: str | None = None,
) -> str:
    """Return a temporary upload URL for the provided object key."""

    settings = get_settings()
    if settings.s3_backend != "minio":
        raise S3OperationError(
            operation="presign_put",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="PresignUnavailable",
            message="Presigned URLs are only supported for the minio backend",
            bucket=settings.s3_bucket,
            key=key,
        )
    client = get_client()
    bucket_name = bucket or settings.s3_bucket
    params: dict[str, Any] = {"Bucket": bucket_name, "Key": key}
    if content_type:
        params["ContentType"] = content_type

    try:
        return client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        raise S3OperationError.from_client_error(
            "generate_presigned_url", exc, bucket=bucket_name, key=key
        ) from exc
def generate_presigned_get_url(
    key: str,
    *,
    bucket: str | None = None,
    expires_in: int = 3600,
    response_headers: Mapping[str, str] | None = None,
) -> str | None:
    """Return a temporary download URL for the provided object key."""

    settings = get_settings()
    if settings.s3_backend != "minio":
        raise S3OperationError(
            operation="presign_get",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="PresignUnavailable",
            message="Presigned URLs are only supported for the minio backend",
            bucket=settings.s3_bucket,
            key=key,
        )
    client = get_client()
    bucket_name = bucket or settings.s3_bucket
    params: dict[str, Any] = {"Bucket": bucket_name, "Key": key}
    if response_headers:
        params.update(response_headers)

    try:
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        raise S3OperationError.from_client_error(
            "generate_presigned_url", exc, bucket=bucket_name, key=key
        ) from exc
