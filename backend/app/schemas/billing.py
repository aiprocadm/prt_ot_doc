from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BillingChangePlanRequest(BaseModel):
    plan_code: str


class BillingOverrideRequest(BaseModel):
    limits: dict[str, Any]
    features: dict[str, Any]


class BillingSummaryRead(BaseModel):
    plan: dict[str, Any]
    subscription: dict[str, Any]
    limits: dict[str, Any]
    features: dict[str, Any]
    usage: dict[str, Any]
    remaining: dict[str, Any]


class BillingInvoiceRead(BaseModel):
    id: str
    period_yyyymm: int
    amount: float
    status: str
    due_date: datetime | None
    payload: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)
