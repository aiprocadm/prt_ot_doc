from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
from typing import Any

from app.services.file_storage import FileStorageService


@dataclass
class DocumentService:
    storage: FileStorageService

    def save(self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False) -> dict[str, Any]:
        meta = self.storage.upload(key, BytesIO(data), content_type=content_type, quarantined=quarantined)
        return {
            "key": key,
            "sha256": hashlib.sha256(data).hexdigest(),
            "storage": meta.to_dict(),
            "audit": {"operation": "save", "quarantined": quarantined, "content_type": content_type},
        }

    def load(self, key: str) -> bytes:
        return self.storage.download(key)

    def head(self, key: str) -> dict[str, Any] | None:
        return self.storage.head(key)

    def signed_download(self, key: str, *, download_name: str | None = None) -> dict[str, Any]:
        meta = self.head(key)
        if meta is None:
            raise KeyError(key)
        return {
            "key": key,
            "signed_url": self.storage.create_signed_url(key, download_name=download_name),
            "meta": meta,
            "download_name": download_name,
            "audit": {"operation": "signed_download", "quarantined": bool(meta.get("quarantined", False))},
        }
