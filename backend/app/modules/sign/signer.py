from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(slots=True)
class DocumentSigner:
    secret: str

    def sign(self, data: bytes) -> str:
        return hashlib.sha256(self.secret.encode("utf-8") + data).hexdigest()
