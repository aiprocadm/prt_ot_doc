from __future__ import annotations

import base64
import hashlib
import hmac
import os
import shutil
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
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


def _clone_blob_meta(meta: BlobMeta) -> BlobMeta:
    return BlobMeta(
        key=meta.key,
        size=meta.size,
        content_type=meta.content_type,
        sha256=meta.sha256,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        quarantined=meta.quarantined,
        adapter=meta.adapter,
        etag=meta.etag,
        scan_status=meta.scan_status,
        tags=dict(meta.tags),
        last_validated_mime=meta.last_validated_mime,
    )


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

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False
    ) -> BlobMeta: ...
    def get(self, key: str) -> bytes: ...
    def head(self, key: str) -> BlobMeta | None: ...
    def has(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...
    def ensure_ready(self) -> None: ...
    def mark_quarantined(
        self, key: str, *, quarantined: bool, reason: str | None = None
    ) -> BlobMeta | None: ...


class _MemoryAdapter:
    name = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Blob] = {}
        self._meta: dict[str, BlobMeta] = {}

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False
    ) -> BlobMeta:
        now = datetime.now(tz=timezone.utc)
        existing = self._meta.get(key)
        meta = BlobMeta(
            key=key,
            size=len(data),
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
            quarantined=quarantined,
            adapter=self.name,
            etag=hashlib.md5(data, usedforsecurity=False).hexdigest(),  # noqa: S324  # nosec B324 - S3-compatible eTag, content fingerprint only
            scan_status="quarantined" if quarantined else "clean",
            tags=dict(existing.tags) if existing is not None else {},
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
            return _clone_blob_meta(meta)

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

    def mark_quarantined(
        self, key: str, *, quarantined: bool, reason: str | None = None
    ) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None:
                return None
            meta.quarantined = quarantined
            meta.updated_at = datetime.now(tz=timezone.utc)
            meta.scan_status = "quarantined" if quarantined else "clean"
            if reason:
                meta.tags["quarantine_reason"] = reason
            return _clone_blob_meta(meta)


class _LocalAdapter:
    name = "local"

    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._meta: dict[str, BlobMeta] = {}
        self._lock = threading.RLock()

    def _path(self, key: str) -> Path:
        return self._root / key

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False
    ) -> BlobMeta:
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
                etag=hashlib.md5(data, usedforsecurity=False).hexdigest(),  # noqa: S324  # nosec B324 - S3-compatible eTag
                scan_status="quarantined" if quarantined else "clean",
                tags=dict(existing.tags) if existing else {},
                last_validated_mime=content_type,
            )
            self._meta[key] = meta
            return _clone_blob_meta(meta)

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
                    etag=hashlib.md5(payload, usedforsecurity=False).hexdigest(),  # noqa: S324  # nosec B324 - S3-compatible eTag
                    scan_status="clean",
                )
                self._meta[key] = meta
            return _clone_blob_meta(meta) if meta else None

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        with self._lock:
            self._meta.pop(key, None)
        self._path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        with self._lock:
            self._meta.clear()
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)
            self._root.mkdir(parents=True, exist_ok=True)

    def ensure_ready(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def mark_quarantined(
        self, key: str, *, quarantined: bool, reason: str | None = None
    ) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None:
                return None
            meta.quarantined = quarantined
            meta.scan_status = "quarantined" if quarantined else "clean"
            meta.updated_at = datetime.now(tz=timezone.utc)
            if reason:
                meta.tags["quarantine_reason"] = reason
            return _clone_blob_meta(meta)


class _S3Adapter:
    name = "s3"

    def __init__(self) -> None:
        from app.modules.files import s3 as s3_domain

        self._s3 = s3_domain
        self._meta: dict[str, BlobMeta] = {}
        self._lock = threading.RLock()

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False
    ) -> BlobMeta:
        now = datetime.now(tz=timezone.utc)
        mime = content_type or "application/octet-stream"
        self._s3.ensure_bucket()
        etag = self._s3.put_object(data=data, mime=mime, key=key)
        with self._lock:
            existing = self._meta.get(key)
            meta = BlobMeta(
                key=key,
                size=len(data),
                content_type=mime,
                sha256=hashlib.sha256(data).hexdigest(),
                created_at=existing.created_at if existing else now,
                updated_at=now,
                quarantined=quarantined,
                adapter=self.name,
                etag=etag or None,
                scan_status="quarantined" if quarantined else "clean",
                tags=dict(existing.tags) if existing else {},
                last_validated_mime=mime,
            )
            self._meta[key] = meta
            return _clone_blob_meta(meta)

    def get(self, key: str) -> bytes:
        self._s3.ensure_bucket()
        with self._s3.stream_object(key=key) as stream:
            return stream.read()

    def head(self, key: str) -> BlobMeta | None:
        remote = self._s3.head_object(key=key)
        if remote is None:
            return None
        with self._lock:
            cached = self._meta.get(key)
            now = datetime.now(tz=timezone.utc)
            meta = BlobMeta(
                key=key,
                size=int(remote.get("size") or (cached.size if cached else 0)),
                content_type=remote.get("content_type")
                or (cached.content_type if cached else None),
                sha256=cached.sha256 if cached else "",
                created_at=cached.created_at if cached else now,
                updated_at=now,
                quarantined=cached.quarantined if cached else False,
                adapter=self.name,
                etag=remote.get("etag") or (cached.etag if cached else None),
                scan_status=cached.scan_status if cached else "pending",
                tags=dict(cached.tags) if cached else {},
                last_validated_mime=(
                    cached.last_validated_mime if cached else remote.get("content_type")
                ),
            )
            self._meta[key] = meta
            return _clone_blob_meta(meta)

    def has(self, key: str) -> bool:
        return self.head(key) is not None

    def delete(self, key: str) -> None:
        with self._lock:
            self._meta.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._meta.clear()

    def ensure_ready(self) -> None:
        self._s3.ensure_bucket()

    def mark_quarantined(
        self, key: str, *, quarantined: bool, reason: str | None = None
    ) -> BlobMeta | None:
        with self._lock:
            meta = self._meta.get(key)
            if meta is None:
                meta = self.head(key)
                if meta is None:
                    return None
                self._meta[key] = meta
            meta.quarantined = quarantined
            meta.scan_status = "quarantined" if quarantined else "clean"
            meta.updated_at = datetime.now(tz=timezone.utc)
            if reason:
                meta.tags["quarantine_reason"] = reason
            return _clone_blob_meta(meta)


class FileStorageService:
    """Storage facade with dev/test memory adapter and production-like local/S3 semantics."""

    _instance: ClassVar[FileStorageService | None] = None
    _instance_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(
        self, *, adapter: StorageAdapter | None = None, signing_secret: str | None = None
    ) -> None:
        self._settings = get_settings()
        self._adapter = adapter or self._build_adapter()
        self._signing_secret = (signing_secret or self._settings.secret_key or "change-me").encode(
            "utf-8"
        )

    @staticmethod
    def _ensure_raw_key_is_valid(key: str) -> None:
        if not key:
            raise ValueError("Storage key must not be empty")
        segments = key.split("/")
        if any(segment == ".." for segment in segments):
            raise ValueError("Storage key must not contain parent directory segments")
        for character in key:
            category = unicodedata.category(character)
            if (character != " " and character.isspace()) or category in {
                "Cc",
                "Cf",
                "Cs",
                "Co",
                "Cn",
            }:
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
        if backend == "s3":
            if self._settings.s3_backend == "local":
                return _LocalAdapter(self._settings.storage_root)
            return _S3Adapter()
        return _MemoryAdapter()

    @classmethod
    def default(cls) -> FileStorageService:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = FileStorageService()
        return cls._instance

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False
    ) -> None:
        normalized_key = self._normalize_key(key)
        self._adapter.put(normalized_key, data, content_type=content_type, quarantined=quarantined)

    def get(self, key: str) -> bytes:
        normalized_key = self._normalize_key(key)
        return self._adapter.get(normalized_key)

    def upload(
        self,
        key: str,
        data: BinaryIO,
        *,
        content_type: str | None = None,
        quarantined: bool = False,
    ) -> BlobMeta:
        payload = data.read()
        if not isinstance(payload, bytes):
            payload = bytes(payload)
        normalized_key = self._normalize_key(key)
        return self._adapter.put(
            normalized_key, payload, content_type=content_type, quarantined=quarantined
        )

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

    def write_temp_file(self, key: str, *, suffix: str | None = None) -> str:
        normalized_key = self._normalize_key(key)
        payload = self.get(normalized_key)
        suffix_value = suffix or Path(normalized_key).suffix or ".bin"
        with NamedTemporaryFile(prefix="prt-storage-", suffix=suffix_value, delete=False) as handle:
            handle.write(payload)
            return handle.name

    def mark_quarantined(
        self, key: str, *, quarantined: bool = True, reason: str | None = None
    ) -> dict[str, object] | None:
        normalized_key = self._normalize_key(key)
        meta = self._adapter.mark_quarantined(
            normalized_key, quarantined=quarantined, reason=reason
        )
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

    def mime_validation_hook_payload(
        self, key: str, *, detected_mime: str | None = None
    ) -> dict[str, object]:
        meta = self.head(key)
        if meta is None:
            raise KeyError(key)
        return {
            "key": meta["key"],
            "declared_mime": meta["content_type"],
            "detected_mime": detected_mime,
            "sha256": meta["sha256"],
        }

    def create_signed_url(
        self, key: str, *, expires_in: int | None = None, download_name: str | None = None
    ) -> str:
        normalized_key = self._normalize_key(key)
        ttl = int(expires_in or self._settings.presign_download_ttl_seconds)
        if getattr(self._adapter, "name", "") == "s3" and self._settings.s3_backend == "minio":
            from app.modules.files.s3 import generate_presigned_get_url

            response_headers = {}
            if download_name:
                response_headers["ResponseContentDisposition"] = (
                    f'attachment; filename="{download_name}"'
                )
            presigned = generate_presigned_get_url(
                normalized_key, expires_in=ttl, response_headers=response_headers or None
            )
            if presigned:
                return presigned
        expires_at = int((datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)).timestamp())
        payload = f"{normalized_key}{JSON_SAFE_SEPARATOR}{expires_at}{JSON_SAFE_SEPARATOR}{download_name or ''}"
        signature = hmac.new(self._signing_secret, payload.encode("utf-8"), hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"memory://signed/{normalized_key}?expires={expires_at}&signature={token}&download={download_name or ''}"

    def verify_signed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        key = parsed.path.replace("/", "", 1).removeprefix("signed/")
        params = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
        try:
            expires = int(params.get("expires", "0"))
        except ValueError:
            return False
        if not key or expires < int(datetime.now(tz=timezone.utc).timestamp()):
            return False
        download = params.get("download", "")
        payload = f"{self._normalize_key(key)}{JSON_SAFE_SEPARATOR}{expires}{JSON_SAFE_SEPARATOR}{download}"
        signature = hmac.new(self._signing_secret, payload.encode("utf-8"), hashlib.sha256).digest()
        expected_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return hmac.compare_digest(expected_signature, params.get("signature", ""))
