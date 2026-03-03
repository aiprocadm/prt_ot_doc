import hashlib

import pytest
from app.modules.files.service import compute_sha256_stream
from app.modules.files.storage import build_tenant_key
from fastapi import HTTPException


def test_build_tenant_key_is_tenant_scoped() -> None:
    key = build_tenant_key(tenant_id="tenant-a", file_id="f1", version_no=2, filename="doc.pdf")
    assert key.startswith("tenant/tenant-a/")
    assert "/f1/v2/" in key


def test_sha256_computation_matches_reference() -> None:
    payload = b"hello world"
    assert hashlib.sha256(payload).hexdigest() == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha256_streaming_matches_reference() -> None:
    chunks = [b"hello ", b"world"]
    assert compute_sha256_stream(chunks) == hashlib.sha256(b"hello world").hexdigest()


@pytest.mark.asyncio
async def test_download_for_not_ready_version_raises() -> None:
    from app.modules.files import service

    class DummySession:
        async def get(self, model, id_):
            class Obj:
                file_id = "f"
                tenant_id = "t"
                status = "quarantined"

            return Obj()

    with pytest.raises(HTTPException) as exc:
        await service.issue_download_url(
            session=DummySession(),
            tenant_id="t",
            file_id="f",
            version_id="v",
            user_id=None,
            ip=None,
            user_agent=None,
        )
    assert exc.value.status_code == 409
