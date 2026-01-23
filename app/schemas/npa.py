"""Pydantic schemas for normative legal acts."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class NpaClauseRead(BaseModel):
    id: str
    code: str = Field(max_length=128)
    text: str

    model_config = {
        "from_attributes": True,
    }


class NpaActRead(BaseModel):
    id: str
    code: str = Field(max_length=128)
    title: str
    edition: str
    valid_from: date | None = None
    valid_to: date | None = None
    clauses: list[NpaClauseRead] = []

    model_config = {
        "from_attributes": True,
    }


class NpaActListResponse(BaseModel):
    items: list[NpaActRead]
