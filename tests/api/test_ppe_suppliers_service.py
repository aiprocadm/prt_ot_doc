"""DB-level tests for the PPE supplier directory service (P10-06)."""

from __future__ import annotations

import pytest

from app.modules.ppe.suppliers import (
    SupplierNameConflict,
    SupplierNotFound,
    create_supplier,
    get_supplier,
    list_suppliers,
    soft_delete_supplier,
    update_supplier,
)
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_create_and_get(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = await create_supplier(session, tenant_id=tenant.id, name="Вендор", inn="7701234567")
        got = await get_supplier(session, tenant.id, sup.id)
        assert got.name == "Вендор"
        assert got.inn == "7701234567"


@pytest.mark.asyncio
async def test_duplicate_name_conflicts(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await create_supplier(session, tenant_id=tenant.id, name="Дубль")
        with pytest.raises(SupplierNameConflict):
            await create_supplier(session, tenant_id=tenant.id, name="Дубль")


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted_and_paginates(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        a = await create_supplier(session, tenant_id=tenant.id, name="A")
        await create_supplier(session, tenant_id=tenant.id, name="B")
        await soft_delete_supplier(session, tenant.id, a.id)
        items, total = await list_suppliers(session, tenant.id, limit=50, offset=0)
        assert total == 1
        assert [s.name for s in items] == ["B"]


@pytest.mark.asyncio
async def test_update_and_missing(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = await create_supplier(session, tenant_id=tenant.id, name="Old")
        updated = await update_supplier(session, tenant.id, sup.id, name="New", contact_phone="+7")
        assert updated.name == "New"
        assert updated.contact_phone == "+7"
        with pytest.raises(SupplierNotFound):
            await get_supplier(session, tenant.id, "nope")


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        sup = await create_supplier(session, tenant_id=t1.id, name="OnlyT1")
        with pytest.raises(SupplierNotFound):
            await get_supplier(session, t2.id, sup.id)


@pytest.mark.asyncio
async def test_update_rename_to_existing_name_conflicts(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await create_supplier(session, tenant_id=tenant.id, name="A")
        b = await create_supplier(session, tenant_id=tenant.id, name="B")
        with pytest.raises(SupplierNameConflict):
            await update_supplier(session, tenant.id, b.id, name="A")


@pytest.mark.asyncio
async def test_get_after_soft_delete_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = await create_supplier(session, tenant_id=tenant.id, name="Gone")
        await soft_delete_supplier(session, tenant.id, sup.id)
        with pytest.raises(SupplierNotFound):
            await get_supplier(session, tenant.id, sup.id)
