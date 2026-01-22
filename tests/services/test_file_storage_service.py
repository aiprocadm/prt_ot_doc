from __future__ import annotations

import pytest

from app.services.file_storage import FileStorageService


def test_file_storage_roundtrip():
    storage = FileStorageService.default()
    storage.put("documents/report.txt", b"hello", content_type="text/plain")

    assert storage.has("documents/report.txt") is True
    assert storage.get("documents/report.txt") == b"hello"


@pytest.mark.parametrize("key", ["", "../escape", "sub/../bad"])
def test_invalid_storage_keys_raise(key: str):
    storage = FileStorageService.default()
    with pytest.raises(ValueError):
        storage.put(key, b"bad")
