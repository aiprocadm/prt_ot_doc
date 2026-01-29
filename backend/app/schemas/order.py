"""Order schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    contract_id: str = Field(..., min_length=1, max_length=36)
    order_number: str = Field(..., min_length=1, max_length=128)
    status: str | None = None
    ordered_at: date | None = None
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=3)

    model_config = ConfigDict(extra="forbid")


class OrderUpdate(BaseModel):
    contract_id: str | None = Field(default=None, min_length=1, max_length=36)
    order_number: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None
    ordered_at: date | None = None
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=3)

    model_config = ConfigDict(extra="forbid")


class OrderRead(BaseModel):
    id: str
    tenant_id: str
    contract_id: str
    order_number: str
    status: str
    ordered_at: date | None = None
    total_amount: float | None = None
    currency: str

    model_config = ConfigDict(from_attributes=True)


class OrderPage(BaseModel):
    items: list[OrderRead]
    total: int

    model_config = ConfigDict(from_attributes=True)
