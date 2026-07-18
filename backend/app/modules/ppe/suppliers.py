"""PPE supplier directory CRUD (P10-06). Thin async service over PPESupplier.

Name is unique per tenant; a duplicate surfaces as SupplierNameConflict (mapped
to 409 by the route). Soft-delete sets deleted_at; lists exclude soft-deleted.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PPESupplier

_UPDATABLE_FIELDS = frozenset({"name", "inn", "contact_email", "contact_phone"})


class SupplierNotFound(Exception):
    def __init__(self, supplier_id: str) -> None:
        super().__init__(f"PPE supplier not found: {supplier_id}")
        self.supplier_id = supplier_id


class SupplierNameConflict(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"PPE supplier name already exists: {name}")
        self.name = name


async def _load_supplier(session: AsyncSession, tenant_id: str, supplier_id: str) -> PPESupplier:
    stmt = select(PPESupplier).where(
        PPESupplier.id == supplier_id,
        PPESupplier.tenant_id == tenant_id,
        PPESupplier.deleted_at.is_(None),
    )
    sup = (await session.execute(stmt)).scalar_one_or_none()
    if sup is None:
        raise SupplierNotFound(supplier_id)
    return sup


async def create_supplier(
    session: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    inn: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> PPESupplier:
    sup = PPESupplier(
        tenant_id=tenant_id,
        name=name,
        inn=inn,
        contact_email=contact_email,
        contact_phone=contact_phone,
    )
    session.add(sup)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplierNameConflict(name) from exc
    await session.refresh(sup)
    return sup


async def get_supplier(session: AsyncSession, tenant_id: str, supplier_id: str) -> PPESupplier:
    return await _load_supplier(session, tenant_id, supplier_id)


async def list_suppliers(
    session: AsyncSession, tenant_id: str, *, limit: int, offset: int
) -> tuple[list[PPESupplier], int]:
    base = (
        PPESupplier.tenant_id == tenant_id,
        PPESupplier.deleted_at.is_(None),
    )
    items = list(
        (
            await session.execute(
                select(PPESupplier)
                .where(*base)
                .order_by(PPESupplier.name.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(select(func.count()).where(*base))).scalar_one()
    return items, int(total or 0)


async def update_supplier(
    session: AsyncSession, tenant_id: str, supplier_id: str, **fields
) -> PPESupplier:
    """Update a supplier. Only keys in ``_UPDATABLE_FIELDS`` are applied; stray
    keys are ignored so they can never ``setattr`` onto the row."""
    sup = await _load_supplier(session, tenant_id, supplier_id)
    for key, value in fields.items():
        if key in _UPDATABLE_FIELDS:
            setattr(sup, key, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplierNameConflict(fields.get("name", sup.name)) from exc
    await session.refresh(sup)
    return sup


async def soft_delete_supplier(session: AsyncSession, tenant_id: str, supplier_id: str) -> None:
    sup = await _load_supplier(session, tenant_id, supplier_id)
    sup.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()
