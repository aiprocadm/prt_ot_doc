from __future__ import annotations

import threading
import unicodedata
from typing import ClassVar, Tuple
from urllib.parse import urlparse

__all__ = ["Blob", "FileStorageService", "_resolve_endpoint"]


def _resolve_endpoint(endpoint: str, *, secure: bool) -> Tuple[str | None, bool]:
    """Normalize an S3 endpoint value to host[:port] and secure flag."""

    if not endpoint:
        return None, secure

    parsed = urlparse(endpoint)
    if parsed.scheme:
        host = parsed.netloc or parsed.path
        is_secure = parsed.scheme.lower() == "https"
        return host, is_secure

    return endpoint, secure


class Blob:
    """Immutable blob stored in memory."""

    __slots__ = ("content", "content_type")

    def __init__(self, content: bytes, content_type: str | None = None) -> None:
        self.content = content
        self.content_type = content_type


class FileStorageService:
    """Thread-safe in-memory storage emulating an object store for tests and local runs."""

    _instance: ClassVar[FileStorageService | None] = None
    _instance_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Blob] = {}

    @staticmethod
    def _ensure_raw_key_is_valid(key: str) -> None:
        """Validate the raw key before any normalization occurs."""

        if not key:
            raise ValueError("Storage key must not be empty")

        segments = key.split("/")
        if any(segment == ".." for segment in segments):
            raise ValueError("Storage key must not contain parent directory segments")

        for character in key:
            category = unicodedata.category(character)
            if (
                (character != " " and character.isspace())
                or category in {"Cc", "Cf", "Cs", "Co", "Cn"}
            ):
                raise ValueError("Storage key must not contain invisible characters")

    @classmethod
    def _normalize_key(cls, key: str) -> str:
        """Return a sanitized storage key.

        The sanitization removes empty and current-directory segments, rejects
        keys with prohibited segments, rejects zero-length results, and enforces
        an upper bound on the resulting key length.
        """

        cls._ensure_raw_key_is_valid(key)
        segments: list[str] = []
        for raw_segment in key.split("/"):
            if not raw_segment or raw_segment == ".":
                continue
            segments.append(raw_segment)

        normalized = "/".join(segments)
        if not normalized:
            raise ValueError("Storage key must not be empty after normalization")
        if len(normalized) > 512:
            raise ValueError("Storage key length must be less than or equal to 512 characters")
        return normalized

    @classmethod
    def default(cls) -> FileStorageService:
        """Return process-wide singleton storage."""

        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = FileStorageService()
        return cls._instance

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        """Store a blob under the provided key."""

        normalized_key = self._normalize_key(key)
        with self._lock:
            self._data[normalized_key] = Blob(data, content_type)

    def get(self, key: str) -> bytes:
        """Retrieve blob content for the key."""

        normalized_key = self._normalize_key(key)
        with self._lock:
            return self._data[normalized_key].content

    def head(self, key: str) -> dict[str, object] | None:
        """Return metadata for a stored blob, if present."""

        normalized_key = self._normalize_key(key)
        with self._lock:
            blob = self._data.get(normalized_key)
            if blob is None:
                return None
            return {
                "key": normalized_key,
                "size": len(blob.content),
                "content_type": blob.content_type,
            }

    def has(self, key: str) -> bool:
        """Check whether key exists."""

        normalized_key = self._normalize_key(key)
        with self._lock:
            return normalized_key in self._data

    def delete(self, key: str) -> None:
        """Remove a stored blob if it exists."""

        normalized_key = self._normalize_key(key)
        with self._lock:
            self._data.pop(normalized_key, None)

    def ensure_ready(self) -> None:
        """Compatibility hook mimicking real storages."""

        return None

    def clear(self) -> None:
        """Remove all stored blobs."""

        with self._lock:
            self._data.clear()
