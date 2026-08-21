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


class BillingPlanRead(BaseModel):
    code: str
    name: str
    limits: dict[str, Any]
    features: dict[str, Any]


class BillingEditionRead(BaseModel):
    """Редакция под размер заказчика (BIZ-53 срез-2, Доп. №1 разд. 53.1).

    Отличается от тарифа тем, что говорит КОМУ подходит, а не из каких флагов
    состоит: «Базовый / Про / Всё включено» этого сказать не могут.
    """

    code: str
    title: str
    #: Профиль заказчика из таблицы ТЗ.
    audience: str
    #: Технический тариф под редакцией.
    plan_code: str
    includes: str
    #: Чем редакция отличается СВЕРХ набора модулей (SSO, on-prem, SLA…).
    #: Пусто там, где тариф у редакции свой.
    beyond_modules: str = ""


class BillingStatusMutationRequest(BaseModel):
    grace_days: int = 7


class BillingEventRead(BaseModel):
    id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
