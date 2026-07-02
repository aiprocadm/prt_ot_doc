"""Schemas for PPE items and issues."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field, field_validator

from app.models.models import PPEIssueStatus, PPEItemCategory
from app.schemas.base import BaseSchema


class PPEItemCreate(BaseSchema):
    name: str
    code: str | None = None
    category: PPEItemCategory = PPEItemCategory.OTHER
    description: str | None = None
    default_wear_days: int = Field(default=365, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() == "feet":
            return PPEItemCategory.FOOTWEAR
        return value


class PPEItemUpdate(BaseSchema):
    name: str | None = None
    code: str | None = None
    category: PPEItemCategory | None = None
    description: str | None = None
    default_wear_days: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() == "feet":
            return PPEItemCategory.FOOTWEAR
        return value


class PPEItemRead(BaseSchema):
    id: str
    name: str
    code: str | None
    category: PPEItemCategory
    description: str | None
    default_wear_days: int
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PPEItemPage(BaseSchema):
    items: list[PPEItemRead]
    total: int


class PPENormCreate(BaseSchema):
    position_id: str
    hazard_id: str
    item_id: str
    quantity: int = Field(default=1, ge=1)
    interval_days: int = Field(default=365, ge=1)


class PPENormUpdate(BaseSchema):
    item_id: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    interval_days: int | None = Field(default=None, ge=1)


class PPENormRead(BaseSchema):
    id: str
    position_id: str
    hazard_id: str
    item_id: str | None
    item_name: str
    quantity: int
    interval_days: int
    created_at: datetime
    updated_at: datetime


class PPENormPage(BaseSchema):
    items: list[PPENormRead]
    total: int


class PPEIssueCreate(BaseSchema):
    person_id: str
    item_id: str
    quantity: int = Field(default=1, ge=1)
    issued_at: datetime | None = None
    wear_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    certificate_no: str | None = Field(default=None, max_length=255)
    wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)
    batch_id: str | None = None  # P10-06: explicit stock batch to deplete (else FIFO)


class PPEIssueUpdate(BaseSchema):
    status: PPEIssueStatus | None = None
    returned_at: datetime | None = None
    expires_at: datetime | None = None
    wear_days: int | None = Field(default=None, ge=1)


class PPEIssueRead(BaseSchema):
    id: str
    person_id: str
    item_id: str | None
    item_name: str
    quantity: int
    issued_at: datetime
    expires_at: datetime | None
    returned_at: datetime | None
    wear_days: int | None
    status: PPEIssueStatus
    certificate_no: str | None
    wear_percent: int | None
    return_wear_percent: int | None
    signature_doc_ref: str | None
    writeoff_reason: str | None
    replaces_issue_id: str | None
    created_at: datetime
    updated_at: datetime


class PPEIssuePage(BaseSchema):
    items: list[PPEIssueRead]
    total: int


class PPEIssueReturnRequest(BaseSchema):
    returned_at: datetime | None = None
    return_wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)


class PPEIssueWriteoffRequest(BaseSchema):
    writeoff_reason: str = Field(min_length=1, max_length=255)


class PPEIssueReplaceRequest(BaseSchema):
    item_id: str | None = None  # default: тот же item, что у заменяемой выдачи
    quantity: int | None = Field(default=None, ge=1)
    wear_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    certificate_no: str | None = Field(default=None, max_length=255)
    wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)
    batch_id: str | None = None  # P10-06: explicit stock batch to deplete (else FIFO)


class PPECardRequiredLine(BaseSchema):
    item_id: str | None
    item_name: str
    required_quantity: int
    interval_days: int | None
    status: str


class PPECardTimelineEvent(BaseSchema):
    occurred_at: datetime
    event: str
    issue_id: str
    item_name: str


class PPECardRead(BaseSchema):
    person_id: str
    full_name: str
    personnel_number: str | None
    hired_at: date | None
    position_name: str | None
    sizes: dict[str, Any] | None
    required: list[PPECardRequiredLine]
    issues: list[PPEIssueRead]
    timeline: list[PPECardTimelineEvent]
    summary_status: str


class PPESizesUpdate(BaseSchema):
    height: int | None = Field(default=None, ge=100, le=250)
    clothing_size: str | None = Field(default=None, max_length=16)
    shoe_size: str | None = Field(default=None, max_length=16)
    headgear_size: str | None = Field(default=None, max_length=16)
    gas_mask_size: str | None = Field(default=None, max_length=16)
    respirator_size: str | None = Field(default=None, max_length=16)
    gloves_size: str | None = Field(default=None, max_length=16)
    mittens_size: str | None = Field(default=None, max_length=16)


class PPESizesRead(BaseSchema):
    person_id: str
    sizes: dict[str, Any] | None


class PPEStockBatchCreate(BaseSchema):
    item_id: str
    batch_no: str
    quantity: int = Field(default=0, ge=0)
    received_at: date | None = None
    certificate_no: str | None = None
    certificate_expires_at: date | None = None
    location: str | None = None


class PPEStockBatchUpdate(BaseSchema):
    batch_no: str | None = None
    received_at: date | None = None
    certificate_no: str | None = None
    certificate_expires_at: date | None = None
    location: str | None = None


class PPEStockBatchRead(BaseSchema):
    id: str
    item_id: str
    batch_no: str
    quantity: int
    received_at: date | None
    certificate_no: str | None
    certificate_expires_at: date | None
    location: str | None
    created_at: datetime
    updated_at: datetime


class PPEStockBatchPage(BaseSchema):
    items: list[PPEStockBatchRead]
    total: int


class PPEStockLevelRead(BaseSchema):
    item_id: str
    item_name: str
    total_quantity: int
    batch_count: int
    nearest_certificate_expiry: date | None


class PPEStockLevelPage(BaseSchema):
    items: list[PPEStockLevelRead]
    total: int


_MOVEMENT_MANUAL_KINDS = {"receipt", "writeoff", "adjustment"}


class PPEStockMovementCreate(BaseSchema):
    batch_id: str
    kind: str
    quantity: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if value not in _MOVEMENT_MANUAL_KINDS:
            raise ValueError(
                "kind must be one of receipt/writeoff/adjustment "
                "(issue movements are created by the issuance flow)"
            )
        return value


class PPEStockMovementRead(BaseSchema):
    id: str
    item_id: str
    batch_id: str | None
    kind: str
    quantity_delta: int
    occurred_at: datetime
    reason: str | None
    ref_type: str | None
    ref_id: str | None
    created_at: datetime


class PPEStockMovementPage(BaseSchema):
    items: list[PPEStockMovementRead]
    total: int
