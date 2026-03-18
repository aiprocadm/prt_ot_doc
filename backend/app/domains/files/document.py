from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from typing import Any

from app.services.file_storage import FileStorageService


@dataclass
class DocumentService:
    storage: FileStorageService

    def save(self, key: str, data: bytes, *, content_type: str | None = None, quarantined: bool = False) -> dict[str, Any]:
        meta = self.storage.upload(key, io.BytesIO(data), content_type=content_type, quarantined=quarantined)
        return {"key": key, "sha256": hashlib.sha256(data).hexdigest(), "storage": meta.to_dict()}

    def load(self, key: str) -> bytes:
        return self.storage.download(key)

    def head(self, key: str) -> dict[str, Any] | None:
        return self.storage.head(key)
