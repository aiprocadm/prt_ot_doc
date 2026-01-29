"""S3/MinIO helper functions with normalized error handling."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import lru_cache
from http import HTTPStatus
from typing import Any, BinaryIO, Iterator, Mapping
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings

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
]


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


@lru_cache(maxsize=1)
def _get_client() -> BaseClient:
    settings = get_settings()
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


def get_client() -> BaseClient:
    """Expose cached S3 client."""

    return _get_client()


def reset_client_cache() -> None:
    """Clear cached S3 client and reload settings on next access."""

    _get_client.cache_clear()
    get_settings.cache_clear()  # type: ignore[attr-defined]


def ensure_bucket() -> None:
    """Ensure the configured bucket exists."""

    client = get_client()
    settings = get_settings()
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


def put_object(*, data: bytes, mime: str, key: str) -> str:
    """Upload object to S3 under provided key and return resulting ETag."""

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes-like")

    client = get_client()
    settings = get_settings()

    try:
        response = client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=mime,
        )
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
            "size": len(data),
        },
    )
    return etag


def head_object(*, key: str) -> dict[str, Any] | None:
    """Fetch object metadata if key exists."""

    client = get_client()
    settings = get_settings()

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

    client = get_client()
    settings = get_settings()

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


def generate_presigned_get_url(
    key: str,
    *,
    bucket: str | None = None,
    expires_in: int = 3600,
    response_headers: Mapping[str, str] | None = None,
) -> str | None:
    """Return a temporary download URL for the provided object key."""

    client = get_client()
    settings = get_settings()
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
