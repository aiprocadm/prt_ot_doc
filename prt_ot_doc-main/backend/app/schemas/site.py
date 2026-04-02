from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class SiteBase(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    geo_json: dict | None = None
    hazard_class: str | None = Field(default=None, max_length=32)
    site_type: str | None = Field(default=None, max_length=64)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    is_hazardous_production_facility: bool = False
    opo_register_number: str | None = Field(default=None, max_length=64)
    branding_payload: dict = Field(default_factory=dict)


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    geo_json: dict | None = None
    hazard_class: str | None = Field(default=None, max_length=32)
    site_type: str | None = Field(default=None, max_length=64)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    is_hazardous_production_facility: bool | None = None
    opo_register_number: str | None = Field(default=None, max_length=64)
    branding_payload: dict | None = None


class SiteRead(SiteBase):
    id: str


class SitePage(BaseSchema):
    items: list[SiteRead]
    total: int


class WorkplaceBase(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    working_conditions_class: str | None = Field(default=None, max_length=32)
    hazard_ids: list[str] = Field(default_factory=list)
    document_file_ids: list[str] = Field(default_factory=list)


class WorkplaceCreate(WorkplaceBase):
    pass


class WorkplaceUpdate(BaseSchema):
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    working_conditions_class: str | None = Field(default=None, max_length=32)
    hazard_ids: list[str] | None = None
    document_file_ids: list[str] | None = None


class WorkplaceRead(WorkplaceBase):
    id: str


class WorkplacePage(BaseSchema):
    items: list[WorkplaceRead]
    total: int
