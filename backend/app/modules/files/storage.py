from __future__ import annotations

from datetime import datetime, timezone

from app.domains.files import s3

_LEGACY_TENANT_PREFIX = "tenant"
_CURRENT_TENANT_PREFIX = "tenants"


def build_tenant_key(
    *,
    tenant_id: str,
    file_id: str,
    filename: str,
    entity: str | None = None,
    entity_id: str | None = None,
    version_no: int | None = None,
) -> str:
    safe_name = filename.replace("..", "_").replace("/", "_")
    now = datetime.now(timezone.utc)
    if entity is None and entity_id is None and version_no is None:
        return f"{_CURRENT_TENANT_PREFIX}/{tenant_id}/{now:%Y/%m/%d}/{file_id}/{safe_name}"
    resolved_entity = str(entity or "files")
    resolved_entity_id = str(entity_id or file_id)
    if version_no is not None:
        return f"{_CURRENT_TENANT_PREFIX}/{tenant_id}/{resolved_entity}/{resolved_entity_id}/{file_id}/v{version_no}/{safe_name}"
    return f"{_CURRENT_TENANT_PREFIX}/{tenant_id}/{resolved_entity}/{resolved_entity_id}/{file_id}_{safe_name}"


def assert_tenant_key(*, tenant_id: str, key: str) -> None:
    # Reject any parent-dir sequence anywhere: ".." covers "../", "..\\" and a
    # leading ".." inside a filename. Consistent with build_tenant_key, which
    # sanitizes ".." out of filenames.
    if ".." in key:
        raise PermissionError("tenant_key_forbidden")
    valid_prefixes = (
        f"{_CURRENT_TENANT_PREFIX}/{tenant_id}/",
        f"{_LEGACY_TENANT_PREFIX}/{tenant_id}/",
    )
    matched_prefix = next((prefix for prefix in valid_prefixes if key.startswith(prefix)), None)
    if matched_prefix is None:
        raise PermissionError("tenant_key_forbidden")
    # The prefix alone is not a valid file key — require a non-empty file component.
    if not key[len(matched_prefix) :].strip("/"):
        raise PermissionError("tenant_key_forbidden")


def presign_get(*, key: str, expires_in: int) -> str:
    url = s3.generate_presigned_get_url(key, expires_in=expires_in)
    if not url:
        raise RuntimeError("failed_to_generate_signed_url")
    return url


def presign_put(*, key: str, expires_in: int) -> str:
    return s3.generate_presigned_put_url(key, expires_in=expires_in)
