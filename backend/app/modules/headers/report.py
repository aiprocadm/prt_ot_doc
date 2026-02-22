from __future__ import annotations

from pydantic import BaseModel, Field


class ApplyHeadersReport(BaseModel):
    changed_parts: list[str] = Field(default_factory=list)
    unresolved_placeholders: list[str] = Field(default_factory=list)
    fields_added: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
