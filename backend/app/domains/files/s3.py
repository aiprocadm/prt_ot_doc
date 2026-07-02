"""Deprecated compat-shim — canonical location is :mod:`app.modules.files.s3` (ARCH-1).

Names re-exported here reference the same function objects as the canon module,
but this is a distinct module object: mock-patch string targets must point at
``app.modules.files.s3.*`` (all in-repo tests already do).
"""

from __future__ import annotations

from app.modules.files.s3 import (  # noqa: F401  (compat re-export)
    S3OperationError,
    _resolve_endpoint,
    ensure_bucket,
    generate_presigned_get_url,
    generate_presigned_put_url,
    get_client,
    head_object,
    put_object,
    reset_client_cache,
    stream_object,
)

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
