import pytest

from app.services.file_storage import FileStorageService


def test_storage_allows_space_in_key() -> None:
    storage = FileStorageService.default()
    storage.clear()

    storage.put("folder/my file.txt", b"content", content_type="text/plain")

    assert storage.has("folder/my file.txt")
    assert storage.get("folder/my file.txt") == b"content"


def test_storage_rejects_other_whitespace() -> None:
    storage = FileStorageService.default()
    storage.clear()

    invalid_key = "folder\tmyfile.txt"
    with pytest.raises(ValueError) as excinfo:
        storage.put(invalid_key, b"content")

    assert "invisible characters" in str(excinfo.value)


def test_storage_rejects_parent_segments() -> None:
    storage = FileStorageService.default()
    storage.clear()

    with pytest.raises(ValueError):
        storage.put("../../etc/passwd", b"nope")


def test_storage_normalizes_redundant_segments() -> None:
    storage = FileStorageService.default()
    storage.clear()

    storage.put("/prefix//./file.txt", b"data")

    assert storage.has("prefix/file.txt")
    assert storage.get("./prefix/./file.txt") == b"data"
