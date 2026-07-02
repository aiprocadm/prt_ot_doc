from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class BranchBase(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    status: str = Field(default="active", max_length=32)


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    status: str | None = Field(default=None, max_length=32)


class BranchRead(BranchBase):
    id: str


class BranchPage(BaseSchema):
    items: list[BranchRead]
    total: int
