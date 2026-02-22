from __future__ import annotations

from app.domains.files import s3


def build_tenant_key(*, tenant_id: str, file_id: str, version_no: int, filename: str) -> str:
    safe_name = filename.replace("..", "_").replace("/", "_")
    return f"{tenant_id}/{file_id}/{version_no}/{safe_name}"


def presign_get(*, key: str, expires_in: int) -> str:
    url = s3.generate_presigned_get_url(key, expires_in=expires_in)
    if not url:
        raise RuntimeError("failed_to_generate_signed_url")
    return url


def presign_put(*, key: str, expires_in: int) -> str:
    return s3.generate_presigned_put_url(key, expires_in=expires_in)
