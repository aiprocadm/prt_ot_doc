from __future__ import annotations

from app.schemas.base import BaseSchema


class TenantRead(BaseSchema):

    id: str
    name: str
    slug: str
    contact_email: str
    is_active: bool


class TenantPage(BaseSchema):
    items: list[TenantRead]
    total: int
