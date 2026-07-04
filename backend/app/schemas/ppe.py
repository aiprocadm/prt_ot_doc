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
    min_stock: int = Field(default=0, ge=0)
    preferred_supplier_id: str | None = None
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
    min_stock: int | None = Field(default=None, ge=0)
    preferred_supplier_id: str | None = None
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
    min_stock: int
    preferred_supplier_id: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PPEItemPage(BaseSchema):
    items: list[PPEItemRead]
    total: int


class PPESupplierCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class PPESupplierUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class PPESupplierRead(BaseSchema):
    id: str
    name: str
    inn: str | None
    contact_email: str | None
    contact_phone: str | None
    created_at: datetime
    updated_at: datetime


class PPESupplierPage(BaseSchema):
    items: list[PPESupplierRead]
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
    supplier_id: str | None = None


class PPEStockBatchUpdate(BaseSchema):
    batch_no: str | None = None
    received_at: date | None = None
    certificate_no: str | None = None
    certificate_expires_at: date | None = None
    location: str | None = None
    supplier_id: str | None = None


class PPEStockBatchRead(BaseSchema):
    id: str
    item_id: str
    batch_no: str
    quantity: int
    received_at: date | None
    certificate_no: str | None
    certificate_expires_at: date | None
    location: str | None
    supplier_id: str | None
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


class PPEStockTransferCreate(BaseSchema):
    source_batch_id: str
    to_location: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None


class PPEStockTransferRead(BaseSchema):
    ref_id: str
    item_id: str
    item_name: str
    batch_no: str
    from_location: str | None
    to_location: str
    quantity: int
    source_batch_id: str
    dest_batch_id: str
    out_movement_id: str
    in_movement_id: str
    reason: str | None
    occurred_at: datetime


class PPEStockTransferPage(BaseSchema):
    items: list[PPEStockTransferRead]
    total: int


class PPEStockLevelByLocationRead(BaseSchema):
    item_id: str
    item_name: str
    location: str | None
    quantity: int
    batch_count: int


class PPEStockLevelByLocationPage(BaseSchema):
    items: list[PPEStockLevelByLocationRead]
    total: int


class PPEStockShortageRead(BaseSchema):
    item_id: str
    item_name: str
    min_stock: int
    on_hand: int
    deficit: int
    below_threshold: bool
    avg_daily_consumption: float
    days_to_depletion: float | None
    projected_breach_date: date | None
    supplier_id: str | None = None
    supplier_name: str | None = None
    supplier_inn: str | None = None
    supplier_contact: str | None = None
    supplier_source: str | None = None


class PPEStockShortagePage(BaseSchema):
    items: list[PPEStockShortageRead]
    total: int
    window_days: int


# Mirrors ``MANUAL_KINDS`` in ``app.modules.ppe.stock`` — intentionally duplicated
# so the schema layer stays free of a service-layer import. Keep the two in sync.
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


class PPEInventoryCountCreate(BaseSchema):
    scope_item_id: str | None = None
    scope_location: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)


class PPEInventoryCountLineInput(BaseSchema):
    line_id: str
    # None = not counted (skipped at apply); 0 = counted-zero (write-off);
    # ge=0 applies only when an int is supplied.
    counted_qty: int | None = Field(default=None, ge=0)


class PPEInventoryCountLinesUpdate(BaseSchema):
    entries: list[PPEInventoryCountLineInput]


class PPEInventoryCountLineRead(BaseSchema):
    id: str
    batch_id: str
    item_id: str
    batch_no: str
    location: str | None
    item_name: str
    system_qty: int
    counted_qty: int | None
    on_hand: int
    delta: int | None
    adjustment_movement_id: str | None


class PPEInventoryCountRead(BaseSchema):
    id: str
    status: str
    scope_item_id: str | None
    scope_location: str | None
    note: str | None
    applied_at: datetime | None
    created_at: datetime
    line_count: int
    counted_count: int


class PPEInventoryCountDetail(PPEInventoryCountRead):
    diff_count: int
    lines: list[PPEInventoryCountLineRead]


class PPEInventoryCountPage(BaseSchema):
    items: list[PPEInventoryCountRead]
    total: int
