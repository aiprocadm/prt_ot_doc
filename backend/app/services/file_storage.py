from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, ClassVar, Protocol, Tuple
from urllib.parse import urlparse

from app.core.config import get_settings

__all__ = [
    "Blob",
    "BlobMeta",
    "FileStorageService",
    "StorageAdapter",
    "_resolve_endpoint",
]


JSON_SAFE_SEPARATOR = ":"


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


@dataclass(frozen=True)
class Blob:
    """Immutable blob payload and content metadata."""

    content: bytes
    content_type: str | None = None


@dataclass
class BlobMeta:
    key: str
    size: int
    content_type: str | None
    sha256: str
    created_at: datetime
    updated_at: datetime
    quarantined: bool = False
    adapter: str = "memory"
    etag: str | None = None
    scan_status: str = "pending"
    tags: dict[str, str] = field(default_factory=dict)
    last_validated_mime: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "size": self.size,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "quarantined": self.quarantined,
            "adapter": self.adapter,
            "etag": self.etag,
            "scan_status": self.scan_status,
            "tags": dict(self.tags),
            "last_validated_mime": self.last_validated_mime,
        }


class StorageAdapter(Protocol):
    name: str

    def put(self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False) -> BlobMeta: ...
    def get(self, key: str) -> bytes: ...
    def head(self, key: str) -> BlobMeta | None: ...
    def has(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...
    def ensure_ready(self) -> None: ...
    def mark_quarantined(self, key: str, *, quarantined: bool, reason: str | None = None) -> BlobMeta | None: ...


class _MemoryAdapter:
    name = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Blob] = {}
        self._meta: dict[str, BlobMeta] = {}

    def put(self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False) -> BlobMeta:
        now = datetime.now(tz=timezone.utc)
        meta = BlobMeta(
            key=key,
            size=len(data),
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            created_at=self._meta.get(key, BlobMeta(key, 0, None, "", now, now)).created_at if key in self._meta else now,
            updated_at=now,
            quarantined=quarantined,
            adapter=self.name,
            etag=hashlib.md5(data).hexdigest(),  # noqa: S324 - eTag compatibility only
            scan_status="quarantined" if quarantined else "clean",
            tags=dict(self._meta.get(key).tags) if key in self._meta else {},
            last_validated_mime=content_type,
        )
        with self._lock:
            self._data[key] = Blob(data, content_type)
            self._meta[key] = meta
        return meta

    def get(self, key: str) -> bytes:
        with self._lock:
            return self._data[key].content

    def head(self, key: str) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None:
                return None
            return BlobMeta(**meta.to_dict())

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._data

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._meta.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._meta.clear()

    def ensure_ready(self) -> None:
        return None

    def mark_quarantined(self, key: str, *, quarantined: bool, reason: str | None = None) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None:
                return None
            meta.quarantined = quarantined
            meta.updated_at = datetime.now(tz=timezone.utc)
            meta.scan_status = "quarantined" if quarantined else "clean"
            if reason:
                meta.tags["quarantine_reason"] = reason
            return BlobMeta(**meta.to_dict())


class _LocalAdapter:
    name = "local"

    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._meta: dict[str, BlobMeta] = {}
        self._lock = threading.RLock()

    def _path(self, key: str) -> Path:
        return self._root / key

    def put(self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False) -> BlobMeta:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
        tmp.write_bytes(data)
        tmp.replace(path)
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            existing = self._meta.get(key)
            meta = BlobMeta(
                key=key,
                size=len(data),
                content_type=content_type,
                sha256=hashlib.sha256(data).hexdigest(),
                created_at=existing.created_at if existing else now,
                updated_at=now,
                quarantined=quarantined,
                adapter=self.name,
                etag=hashlib.md5(data).hexdigest(),  # noqa: S324
                scan_status="quarantined" if quarantined else "clean",
                tags=dict(existing.tags) if existing else {},
                last_validated_mime=content_type,
            )
            self._meta[key] = meta
            return BlobMeta(**meta.to_dict())

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def head(self, key: str) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None and self._path(key).exists():
                payload = self._path(key).read_bytes()
                now = datetime.now(tz=timezone.utc)
                meta = BlobMeta(
                    key=key,
                    size=len(payload),
                    content_type=None,
                    sha256=hashlib.sha256(payload).hexdigest(),
                    created_at=now,
                    updated_at=now,
                    adapter=self.name,
                    etag=hashlib.md5(payload).hexdigest(),  # noqa: S324
                    scan_status="clean",
                )
                self._meta[key] = meta
            return BlobMeta(**meta.to_dict()) if meta else None

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        with self._lock:
            self._meta.pop(key, None)
        self._path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        if self._root.exists():
            for path in sorted(self._root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
        with self._lock:
            self._meta.clear()

    def ensure_ready(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def mark_quarantined(self, key: str, *, quarantined: bool, reason: str | None = None) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None:
                return None
            meta.quarantined = quarantined
            meta.scan_status = "quarantined" if quarantined else "clean"
            meta.updated_at = datetime.now(tz=timezone.utc)
            if reason:
                meta.tags["quarantine_reason"] = reason
            return BlobMeta(**meta.to_dict())


class FileStorageService:
    """Storage facade with dev/test memory adapter and production-like local/S3 semantics."""

    _instance: ClassVar[FileStorageService | None] = None
    _instance_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self, *, adapter: StorageAdapter | None = None, signing_secret: str | None = None) -> None:
        self._settings = get_settings()
        self._adapter = adapter or self._build_adapter()
        self._signing_secret = (signing_secret or self._settings.secret_key or "change-me").encode("utf-8")

    @staticmethod
    def _ensure_raw_key_is_valid(key: str) -> None:
        if not key:
            raise ValueError("Storage key must not be empty")
        segments = key.split("/")
        if any(segment == ".." for segment in segments):
            raise ValueError("Storage key must not contain parent directory segments")
        for character in key:
            category = unicodedata.category(character)
            if ((character != " " and character.isspace()) or category in {"Cc", "Cf", "Cs", "Co", "Cn"}):
                raise ValueError("Storage key must not contain invisible characters")

    @classmethod
    def _normalize_key(cls, key: str) -> str:
        cls._ensure_raw_key_is_valid(key)
        segments = [segment for segment in key.split("/") if segment and segment != "."]
        normalized = "/".join(segments)
        if not normalized:
            raise ValueError("Storage key must not be empty after normalization")
        if len(normalized) > 512:
            raise ValueError("Storage key length must be less than or equal to 512 characters")
        return normalized

    def _build_adapter(self) -> StorageAdapter:
        backend = self._settings.storage_backend
        if backend == "local":
            return _LocalAdapter(self._settings.storage_root)
        if backend == "s3" and self._settings.s3_backend == "local":
            return _LocalAdapter(self._settings.storage_root)
        return _MemoryAdapter()

    @classmethod
    def default(cls) -> FileStorageService:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = FileStorageService()
        return cls._instance

    def put(self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False) -> None:
        normalized_key = self._normalize_key(key)
        self._adapter.put(normalized_key, data, content_type=content_type, quarantined=quarantined)

    def get(self, key: str) -> bytes:
        normalized_key = self._normalize_key(key)
        return self._adapter.get(normalized_key)

    def upload(self, key: str, data: BinaryIO, *, content_type: str | None = None, quarantined: bool = False) -> BlobMeta:
        payload = data.read()
        if not isinstance(payload, bytes):
            payload = bytes(payload)
        normalized_key = self._normalize_key(key)
        return self._adapter.put(normalized_key, payload, content_type=content_type, quarantined=quarantined)

    def download(self, key: str) -> bytes:
        return self.get(key)

    def head(self, key: str) -> dict[str, object] | None:
        normalized_key = self._normalize_key(key)
        meta = self._adapter.head(normalized_key)
        return None if meta is None else meta.to_dict()

    def has(self, key: str) -> bool:
        normalized_key = self._normalize_key(key)
        return self._adapter.has(normalized_key)

    def delete(self, key: str) -> None:
        normalized_key = self._normalize_key(key)
        self._adapter.delete(normalized_key)

    def ensure_ready(self) -> None:
        self._adapter.ensure_ready()

    def clear(self) -> None:
        self._adapter.clear()

    def open_temp(self, key: str) -> BytesIO:
        return BytesIO(self.get(key))

    def mark_quarantined(self, key: str, *, quarantined: bool = True, reason: str | None = None) -> dict[str, object] | None:
        normalized_key = self._normalize_key(key)
        meta = self._adapter.mark_quarantined(normalized_key, quarantined=quarantined, reason=reason)
        return None if meta is None else meta.to_dict()

    def antivirus_scan_hook_payload(self, key: str) -> dict[str, object]:
        meta = self.head(key)
        if meta is None:
            raise KeyError(key)
        return {
            "key": meta["key"],
            "sha256": meta["sha256"],
            "size": meta["size"],
            "content_type": meta["content_type"],
            "quarantined": meta["quarantined"],
        }

    def mime_validation_hook_payload(self, key: str, *, detected_mime: str | None = None) -> dict[str, object]:
        meta = self.head(key)
        if meta is None:
            raise KeyError(key)
        return {
            "key": meta["key"],
            "declared_mime": meta["content_type"],
            "detected_mime": detected_mime,
            "sha256": meta["sha256"],
        }

    def create_signed_url(self, key: str, *, expires_in: int | None = None, download_name: str | None = None) -> str:
        normalized_key = self._normalize_key(key)
        ttl = int(expires_in or self._settings.presign_download_ttl_seconds)
        expires_at = int((datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)).timestamp())
        payload = f"{normalized_key}{JSON_SAFE_SEPARATOR}{expires_at}{JSON_SAFE_SEPARATOR}{download_name or ''}"
        signature = hmac.new(self._signing_secret, payload.encode("utf-8"), hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"memory://signed/{normalized_key}?expires={expires_at}&signature={token}&download={download_name or ''}"

    def verify_signed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        key = parsed.path.replace("/", "", 1).removeprefix("signed/")
        params = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
        expires = int(params.get("expires", "0"))
        if expires < int(datetime.now(tz=timezone.utc).timestamp()):
            return False
        download = params.get("download", "")
        expected = self.create_signed_url(key, expires_in=max(expires - int(datetime.now(tz=timezone.utc).timestamp()), 1), download_name=download)
        expected_params = dict(item.split("=", 1) for item in urlparse(expected).query.split("&") if "=" in item)
        return hmac.compare_digest(expected_params.get("signature", ""), params.get("signature", ""))
