from __future__ import annotations

from io import BytesIO

import pytest

from app.services.file_storage import FileStorageService


def test_file_storage_roundtrip():
    storage = FileStorageService.default()
    storage.clear()
    storage.put("documents/report.txt", b"hello", content_type="text/plain")

    assert storage.has("documents/report.txt") is True
    assert storage.get("documents/report.txt") == b"hello"


@pytest.mark.parametrize("key", ["", "../escape", "sub/../bad"])
def test_invalid_storage_keys_raise(key: str):
    storage = FileStorageService.default()
    with pytest.raises(ValueError):
        storage.put(key, b"bad")


def test_file_storage_supports_signed_urls_and_quarantine_metadata():
    storage = FileStorageService.default()
    storage.clear()

    meta = storage.upload("packages/demo/result.pdf", BytesIO(b"payload"), content_type="application/pdf", quarantined=True)
    signed_url = storage.create_signed_url("packages/demo/result.pdf", download_name="result.pdf")
    head = storage.head("packages/demo/result.pdf")
    hook = storage.antivirus_scan_hook_payload("packages/demo/result.pdf")

    assert meta.quarantined is True
    assert signed_url.startswith("memory://signed/packages/demo/result.pdf")
    assert head is not None
    assert head["quarantined"] is True
    assert head["sha256"] == hook["sha256"]

    updated = storage.mark_quarantined("packages/demo/result.pdf", quarantined=False, reason="scan-clean")
    assert updated is not None
    assert updated["quarantined"] is False
    assert updated["scan_status"] == "clean"
