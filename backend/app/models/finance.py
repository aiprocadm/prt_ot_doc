"""Finance and organizational core entities."""

from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum

__all__ = [
    "Contract",
    "ContractStatus",
    "Department",
    "Invoice",
    "InvoiceStatus",
    "Order",
    "OrderStatus",
]


class Department(TenantBaseModel, SoftDeleteMixin):
    """Tenant-scoped department."""

    __tablename__ = "department"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    company = relationship("Company", backref="departments")

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "name", name="uq_department_company_name"),
        Index("ix_department_company", "tenant_id", "company_id"),
    )


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    TERMINATED = "terminated"


class Contract(TenantBaseModel, SoftDeleteMixin):
    """Tenant contract with optional site linkage."""

    __tablename__ = "contract"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_number: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[ContractStatus] = mapped_column(
        native_enum(ContractStatus, name="contractstatus"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )
    signed_at: Mapped[date | None] = mapped_column(Date)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    company = relationship("Company", backref="contracts")
    department = relationship("Department", backref="contracts")
    site = relationship("Site", backref="contracts")

    __table_args__ = (Index("ix_contract_company", "tenant_id", "company_id"),)


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class Order(TenantBaseModel, SoftDeleteMixin):
    """Order linked to a contract."""

    __tablename__ = "order"

    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contract.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_number: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        native_enum(OrderStatus, name="orderstatus"), nullable=False, default=OrderStatus.DRAFT
    )
    ordered_at: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    contract = relationship("Contract", backref="orders")

    __table_args__ = (
        UniqueConstraint("tenant_id", "contract_id", "order_number", name="uq_order_number"),
        Index("ix_order_contract", "tenant_id", "contract_id"),
    )


class InvoiceStatus(str, enum.Enum):
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"


class Invoice(TenantBaseModel, SoftDeleteMixin):
    """Invoice or act linked to an order/contract."""

    __tablename__ = "invoice"

    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contract.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("order.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        native_enum(InvoiceStatus, name="invoicestatus"),
        nullable=False,
        default=InvoiceStatus.ISSUED,
    )
    issued_at: Mapped[date | None] = mapped_column(Date)
    due_at: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    contract = relationship("Contract", backref="invoices")
    order = relationship("Order", backref="invoices")

    __table_args__ = (
        UniqueConstraint("tenant_id", "contract_id", "invoice_number", name="uq_invoice_number"),
        Index("ix_invoice_contract", "tenant_id", "contract_id"),
    )
