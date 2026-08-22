from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, EmailStr, Field, field_validator

from app.schemas.base import BaseSchema


class CompanyCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    # BIZ-53 (разд. 53.3): головная компания группы. Существование/циклы
    # проверяет API-слой — схема держит только форму значения.
    parent_company_id: str | None = Field(default=None, min_length=1, max_length=36)
    inn: str | None = Field(
        default=None,
        max_length=32,
        validation_alias=AliasChoices("inn", "tax_id"),
        serialization_alias="inn",
    )
    kpp: str | None = Field(default=None, max_length=32)
    ogrn: str | None = Field(default=None, max_length=32)
    activity_type: str | None = Field(default=None, max_length=128)
    okved_codes: list[str] = Field(default_factory=list)
    legal_address: str | None = Field(
        default=None,
        max_length=255,
        validation_alias=AliasChoices("legal_address", "address"),
        serialization_alias="legal_address",
    )
    actual_address: str | None = Field(default=None, max_length=255)
    director: str | None = Field(default=None, max_length=255)
    bank_name: str | None = Field(default=None, max_length=255)
    bank_bik: str | None = Field(default=None, max_length=32)
    bank_account: str | None = Field(default=None, max_length=32)
    phone_numbers: list[str] = Field(default_factory=list)
    contact_person: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    email: EmailStr | None = None
    logo_file_id: str | None = Field(default=None, min_length=1, max_length=36)
    stamp_file_id: str | None = Field(default=None, min_length=1, max_length=36)
    branding_payload: dict[str, Any] = Field(default_factory=dict)
    preferred_header_preset_code: str | None = Field(default=None, max_length=64)
    work_types: list[str] = Field(default_factory=list)
    hazardous_factors: list[str] = Field(default_factory=list)
    is_hazardous_production_facility: bool = False
    has_dangerous_objects: bool = False
    status: str = Field(default="active", max_length=32)
    tags: list[str] = Field(default_factory=list)


class CompanyRead(BaseSchema):
    id: str
    name: str
    parent_company_id: str | None = None
    inn: str | None = Field(default=None, serialization_alias="inn")
    kpp: str | None = None
    ogrn: str | None = None
    activity_type: str | None = None
    okved_codes: list[str] = Field(default_factory=list)
    legal_address: str | None = None
    actual_address: str | None = None
    director: str | None = None
    bank_name: str | None = None
    bank_bik: str | None = None
    bank_account: str | None = None
    phone_numbers: list[str] = Field(default_factory=list)
    contact_person: str | None = None
    contact_phone: str | None = None
    contact_email: EmailStr | None = None
    email: EmailStr | None = None
    logo_file_id: str | None = None
    stamp_file_id: str | None = None
    branding_payload: dict[str, Any] = Field(default_factory=dict)
    preferred_header_preset_code: str | None = None
    work_types: list[str] = Field(default_factory=list)
    hazardous_factors: list[str] = Field(default_factory=list)
    is_hazardous_production_facility: bool = False
    has_dangerous_objects: bool = False
    status: str = Field(default="active", max_length=32)
    tags: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _status_default(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "active"
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_default(cls, value: object) -> object:
        return value if isinstance(value, list) else []


class CompanyPage(BaseSchema):
    items: list[CompanyRead]
    total: int


class CompanyUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # None в exclude_unset-режиме означает «снять привязку к группе».
    parent_company_id: str | None = Field(default=None, max_length=36)
    inn: str | None = Field(
        default=None,
        max_length=32,
        validation_alias=AliasChoices("inn", "tax_id"),
        serialization_alias="inn",
    )
    kpp: str | None = Field(default=None, max_length=32)
    ogrn: str | None = Field(default=None, max_length=32)
    activity_type: str | None = Field(default=None, max_length=128)
    okved_codes: list[str] | None = None
    legal_address: str | None = Field(
        default=None,
        max_length=255,
        validation_alias=AliasChoices("legal_address", "address"),
        serialization_alias="legal_address",
    )
    actual_address: str | None = Field(default=None, max_length=255)
    director: str | None = Field(default=None, max_length=255)
    bank_name: str | None = Field(default=None, max_length=255)
    bank_bik: str | None = Field(default=None, max_length=32)
    bank_account: str | None = Field(default=None, max_length=32)
    phone_numbers: list[str] | None = None
    contact_person: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    email: EmailStr | None = None
    logo_file_id: str | None = Field(default=None, min_length=1, max_length=36)
    stamp_file_id: str | None = Field(default=None, min_length=1, max_length=36)
    branding_payload: dict[str, Any] | None = None
    preferred_header_preset_code: str | None = Field(default=None, max_length=64)
    work_types: list[str] | None = None
    hazardous_factors: list[str] | None = None
    is_hazardous_production_facility: bool | None = None
    has_dangerous_objects: bool | None = None
    status: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None
