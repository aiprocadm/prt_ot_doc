"""BIZ-49 (разд. 49.1): ORM-модель ведомого клиента аутсорсера.

Отдельный bounded context вне трёхтысячестрочного ``models.py`` (та же причина,
что у ``committees.py``). Native enums через ``native_enum`` — по дисциплине
enum-pg-label-parity.

**Клиент — не арендатор.** У одного аутсорсера-арендатора десятки ведомых
клиентов внутри его пространства, поэтому строка tenant-scoped. Ссылка на
собственного арендатора клиента (режим Dedicated) хранится СЛУГОМ, а не FK:
таблица арендаторов живёт в общей схеме, и жёсткая связь потянула бы
cross-schema FK, который проект уже однажды снимал (миграция wa02).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class ManagedClient(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "managed_client"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[ManagedClientMode] = mapped_column(
        native_enum(ManagedClientMode, name="managedclientmode"), nullable=False
    )
    #: Организация клиента в пространстве аутсорсера (обязательна для Lightweight;
    #: у Dedicated остаётся ссылкой на историю после перевода).
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    #: Слуг собственного арендатора клиента (режим Dedicated).
    dedicated_tenant_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)

    contract_status: Mapped[ContractStatus] = mapped_column(
        native_enum(ContractStatus, name="managedclientcontractstatus"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )
    contract_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contract_starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Ответственный специалист аутсорсера (загрузка по портфелю — разд. 49.2).
    responsible_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_managed_client_name"),
        Index("ix_managed_client_tenant_status", "tenant_id", "contract_status"),
    )
