from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RenderPreviewRequest(BaseModel):
    code: str
    version: int
    data: dict[str, Any]
    visible_passport: bool = False


class RenderPreviewResponse(BaseModel):
    file_id: str
    sha256: str
    passport: dict[str, Any]
    warnings: list[str]
    generated_at: datetime
