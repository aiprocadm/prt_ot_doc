from __future__ import annotations

from dataclasses import dataclass
import io

from app.services.file_storage import FileStorageService


@dataclass
class DocumentService:
    storage: FileStorageService

    def save(self, key: str, data: bytes) -> str:
        self.storage.upload(key, io.BytesIO(data))
        return key

    def load(self, key: str) -> bytes:
        return self.storage.download(key)
