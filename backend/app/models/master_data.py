"""Master-data ORM models (company, position, person, site, workplace) — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.file import File
    from app.models.models import (
        Company,
        Person,
        Position,
        Site,
        Workplace,
    )
    from app.models.risk import RiskHazard


class Company(TenantBaseModel, SoftDeleteMixin):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column("tax_id", String(32), nullable=True)
    kpp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    okved_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    legal_address: Mapped[str | None] = mapped_column("address", String(255))
    actual_address: Mapped[str | None] = mapped_column(String(255))
    director: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    bank_bik: Mapped[str | None] = mapped_column(String(32))
    bank_account: Mapped[str | None] = mapped_column(String(32))
    phone_numbers: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    contact_person: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    email: Mapped[str | None] = mapped_column(String(320))
    logo_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    stamp_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    branding_payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    preferred_header_preset_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_types: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    hazardous_factors: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    is_hazardous_production_facility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    has_dangerous_objects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # CRM-статус карточки компании (draft/active/archived) — VARCHAR, не PG-enum
    # (снимает класс enum-parity). tags — свободные метки; nullable, чтобы add_column
    # на существующую таблицу не требовал server_default на JSON.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    tags: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(JSON), nullable=True, default=list
    )

    logo_file: Mapped["File | None"] = relationship(
        "File", foreign_keys=[logo_file_id], lazy="selectin"
    )
    stamp_file: Mapped["File | None"] = relationship(
        "File", foreign_keys=[stamp_file_id], lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_company_tenant_name"),)

    tax_id = synonym("inn")
    address = synonym("legal_address")


class Position(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    safety_category: Mapped[str | None] = mapped_column(String(64))
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))
    hazardous_factors: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    company: Mapped[Company] = relationship(backref="positions")
    hazards: Mapped[list["RiskHazard"]] = relationship(
        "RiskHazard",
        secondary="position_hazard",
        lazy="selectin",
        back_populates="positions",
        overlaps="hazard_links,position,hazard",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "name", name="uq_position_company_name"),
    )


class EmploymentStatus(str, enum.Enum):
    """Employment state for personnel records."""

    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class Person(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("position.id"))
    workplace_id: Mapped[str | None] = mapped_column(ForeignKey("workplace.id"))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    personnel_number: Mapped[str | None] = mapped_column(String(32), index=True)
    hired_at: Mapped[date | None] = mapped_column(Date)
    qualifications: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    snils: Mapped[str | None] = mapped_column(String(32))
    passport: Mapped[str | None] = mapped_column(String(64))
    current_ppe: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    # 766н: рост и размеры СИЗ работника (одежда/обувь/головной убор/СИЗОД/
    # перчатки/рукавицы). JSON: состав ключей зависит от выдаваемых СИЗ.
    ppe_sizes: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))
    hazardous_factors: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    # Свободнотекстовая должность (то, что вводит пользователь во фронте). Отдельно
    # от структурного position_id/relationship `position` (каталог Position) — имя
    # `position` занято связью, поэтому колонка называется position_title.
    position_title: Mapped[str | None] = mapped_column(String(255))
    # values_callable: SQLAlchemy ``Enum`` defaults to sending the Python
    # enum member *name* ("ACTIVE"), but the PG type ``employmentstatus``
    # was created with lowercase *values* ("active") in migration
    # 8d2c1a6c5e24. Override to send ``.value`` so INSERTs satisfy the
    # enum's accepted-value set. Without this, demo bootstrap fails with
    # ``InvalidTextRepresentationError: invalid input value for enum
    # employmentstatus: "ACTIVE"``.
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(
            EmploymentStatus,
            name="employmentstatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EmploymentStatus.ACTIVE,
    )
    # SEC-66 (разд. 66.2): момент обезличивания. Не NULL — прямые идентификаторы
    # необратимо вычищены, а связанные записи (обучение, медосмотры, СИЗ) намеренно
    # сохранены обезличенными: их удаления требует субъект, а хранения — закон.
    # Подробности того, что вычищено, лежат в ``pdn_erasure_record``.
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(backref="people")
    position: Mapped[Position | None] = relationship(backref="people")
    workplace: Mapped["Workplace | None"] = relationship(backref="people")

    __table_args__ = (
        UniqueConstraint("tenant_id", "personnel_number", name="uq_person_tenant_tab_number"),
    )


class Branch(TenantBaseModel, SoftDeleteMixin):
    """Филиал — уровень master-data между Company и Site (RC-014).

    vNext-иерархия: группы компаний → компании → **филиалы** → объекты →
    площадки → подразделения. До этой сущности филиалы моделировались через
    ``Site``; ``Site.branch_id`` — обратная (опциональная) привязка.
    ``status`` — VARCHAR, не PG-enum (снимает класс enum-parity, прецедент cm01).
    """

    __tablename__ = "branch"

    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )

    company: Mapped[Company] = relationship(backref="branches")

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "name", name="uq_branch_company_name"),
    )


class Site(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "site"

    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    # RC-014: привязка к филиалу — app-level reference БЕЗ DB FK: колонка ДОБАВЛЯЕТСЯ
    # к существующей таблице, а add_column с FK — класс миграционных граблей wa02
    # (прецедент: contractor_registry.company_id). Целостность обеспечивает API-слой.
    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    geo_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    hazard_class: Mapped[str | None] = mapped_column(String(32))
    site_type: Mapped[str | None] = mapped_column(String(64))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    is_hazardous_production_facility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    opo_register_number: Mapped[str | None] = mapped_column(String(64))
    branding_payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    company: Mapped[Company] = relationship(backref="sites")


class Workplace(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "workplace"

    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))

    company: Mapped[Company] = relationship(backref="workplaces")
    site: Mapped[Site | None] = relationship(backref="workplaces")
    hazards: Mapped[list["RiskHazard"]] = relationship(
        "RiskHazard",
        secondary="workplace_hazard",
        lazy="selectin",
        back_populates="workplaces",
        overlaps="hazard_links,workplace,hazard",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "name", name="uq_workplace_company_name"),
    )
