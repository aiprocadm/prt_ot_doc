"""Contract schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ContractCreate(BaseModel):
    company_id: str = Field(..., min_length=1, max_length=36)
    department_id: str | None = Field(default=None, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    title: str = Field(..., min_length=1, max_length=255)
    counterparty_name: str = Field(..., min_length=1, max_length=255)
    contract_number: str | None = Field(default=None, max_length=128)
    status: str | None = None
    signed_at: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=3)

    model_config = ConfigDict(extra="forbid")


class ContractUpdate(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=36)
    department_id: str | None = Field(default=None, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    counterparty_name: str | None = Field(default=None, min_length=1, max_length=255)
    contract_number: str | None = Field(default=None, max_length=128)
    status: str | None = None
    signed_at: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=3)

    model_config = ConfigDict(extra="forbid")


class ContractRead(BaseModel):
    id: str
    tenant_id: str
    company_id: str
    department_id: str | None = None
    site_id: str | None = None
    title: str
    counterparty_name: str
    contract_number: str | None = None
    status: str
    signed_at: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    total_amount: float | None = None
    currency: str

    model_config = ConfigDict(from_attributes=True)


class ContractPage(BaseModel):
    items: list[ContractRead]
    total: int

    model_config = ConfigDict(from_attributes=True)
