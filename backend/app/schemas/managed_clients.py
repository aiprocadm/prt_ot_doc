"""Pydantic-схемы ведомых клиентов (BIZ-49 срез-1)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from app.domains.managed_clients.attention import AggregationStatus, Severity, SignalKind
from app.domains.managed_clients.calendar import DeadlineKind
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.schemas.base import BaseSchema


def _strip_required(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Название клиента не может быть пустым")
    return cleaned


class ManagedClientCreate(BaseSchema):
    name: str = Field(max_length=255)
    mode: ManagedClientMode
    company_id: str | None = None
    dedicated_tenant_slug: str | None = Field(default=None, max_length=64)
    contract_no: str | None = Field(default=None, max_length=128)
    contract_starts_at: date | None = None
    contract_ends_at: date | None = None
    responsible_person_id: str | None = None
    notes: str | None = None

    _name_not_blank = field_validator("name")(_strip_required)


class ManagedClientUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    mode: ManagedClientMode | None = None
    company_id: str | None = None
    dedicated_tenant_slug: str | None = Field(default=None, max_length=64)
    contract_status: ContractStatus | None = None
    contract_no: str | None = Field(default=None, max_length=128)
    contract_starts_at: date | None = None
    contract_ends_at: date | None = None
    responsible_person_id: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _strip_required(value)


class ManagedClientRead(BaseSchema):
    id: str
    name: str
    mode: ManagedClientMode
    company_id: str | None
    dedicated_tenant_slug: str | None
    contract_status: ContractStatus
    contract_no: str | None
    contract_starts_at: date | None
    contract_ends_at: date | None
    responsible_person_id: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PortfolioItem(ManagedClientRead):
    """Строка портфеля: карточка клиента + вычисленные сигналы (разд. 49.2)."""

    contract_days_left: int | None = None
    contract_expiring: bool = False


class PortfolioSummary(BaseSchema):
    total: int = 0
    active: int = 0
    draft: int = 0
    suspended: int = 0
    terminated: int = 0
    lightweight: int = 0
    dedicated: int = 0
    contracts_expiring: int = 0


class PortfolioPage(BaseSchema):
    items: list[PortfolioItem]
    summary: PortfolioSummary
    total: int
    limit: int
    offset: int


# --- Cross-client attention (срез-2, разд. 49.2) ---
class AttentionSignalRead(BaseSchema):
    kind: SignalKind
    count: int
    severity: Severity
    title: str
    action_hint: str


class ClientAttentionRead(BaseSchema):
    client_id: str
    client_name: str
    aggregation: AggregationStatus
    signals: list[AttentionSignalRead]
    #: ``None`` = данные клиента в этом срезе не собирались (свой контур).
    total: int | None = None
    severity: Severity | None = None
    reason: str | None = None


class CrossClientAttentionSummary(BaseSchema):
    clients_total: int = 0
    clients_with_signals: int = 0
    clients_not_aggregated: int = 0
    signals_total: int = 0
    critical_clients: int = 0


class CrossClientAttentionResponse(BaseSchema):
    generated_at: datetime
    summary: CrossClientAttentionSummary
    items: list[ClientAttentionRead]


# --- Cross-client календарь (срез-4, разд. 49.2) ---
class DeadlineEventRead(BaseSchema):
    kind: DeadlineKind
    title: str
    due_date: date
    client_id: str
    client_name: str
    subject: str
    responsible_person_id: str | None = None
    days_left: int
    overdue: bool


class DeadlineDayRead(BaseSchema):
    due_date: date
    overdue: bool
    events: list[DeadlineEventRead]


class CalendarSummary(BaseSchema):
    events_total: int = 0
    overdue: int = 0
    due_today: int = 0
    upcoming: int = 0
    clients_touched: int = 0


class CrossClientCalendarResponse(BaseSchema):
    generated_at: datetime
    horizon_days: int
    summary: CalendarSummary
    days: list[DeadlineDayRead]
