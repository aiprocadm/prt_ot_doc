"""Invoice schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class InvoiceCreate(BaseModel):
    contract_id: str = Field(..., min_length=1, max_length=36)
    order_id: str | None = Field(default=None, max_length=36)
    invoice_number: str = Field(..., min_length=1, max_length=128)
    status: str | None = None
    issued_at: date | None = None
    due_at: date | None = None
    paid_at: date | None = None
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=3)

    model_config = ConfigDict(extra="forbid")


class InvoiceUpdate(BaseModel):
    contract_id: str | None = Field(default=None, min_length=1, max_length=36)
    order_id: str | None = Field(default=None, max_length=36)
    invoice_number: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None
    issued_at: date | None = None
    due_at: date | None = None
    paid_at: date | None = None
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=3)

    model_config = ConfigDict(extra="forbid")


class InvoiceRead(BaseModel):
    id: str
    tenant_id: str
    contract_id: str
    order_id: str | None = None
    invoice_number: str
    status: str
    issued_at: date | None = None
    due_at: date | None = None
    paid_at: date | None = None
    total_amount: float | None = None
    currency: str

    model_config = ConfigDict(from_attributes=True)


class InvoicePage(BaseModel):
    items: list[InvoiceRead]
    total: int

    model_config = ConfigDict(from_attributes=True)
