from __future__ import annotations

from datetime import datetime, timezone

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import BriefingEntry, BriefingJournal, BriefingTemplate, Tenant
from app.modules.briefings.services import BriefingEntryService
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/briefings", tags=["briefings"])


@router.get("/templates")
async def list_templates(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(BriefingTemplate).where(BriefingTemplate.tenant_id == tenant.id, BriefingTemplate.deleted_at.is_(None)))).scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/templates")
async def create_template(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = BriefingTemplate(tenant_id=tenant.id, **payload)
    session.add(item)
    await session.flush()
    return item


@router.patch("/templates/{item_id}")
async def patch_template(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingTemplate, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Template not found")
    for k, v in payload.items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/templates/{item_id}", status_code=204)
async def delete_template(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingTemplate, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Template not found")
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.get("/journals")
async def list_journals(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(BriefingJournal).where(BriefingJournal.tenant_id == tenant.id, BriefingJournal.deleted_at.is_(None)))).scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/journals")
async def create_journal(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = BriefingJournal(tenant_id=tenant.id, **payload)
    session.add(item)
    await session.flush()
    return item


@router.patch("/journals/{item_id}")
async def patch_journal(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingJournal, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Journal not found")
    for k, v in payload.items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/journals/{item_id}", status_code=204)
async def delete_journal(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingJournal, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Journal not found")
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.get("/entries")
async def list_entries(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(BriefingEntry).where(BriefingEntry.tenant_id == tenant.id, BriefingEntry.deleted_at.is_(None)))).scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/entries")
async def create_entry(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = BriefingEntry(tenant_id=tenant.id, **payload)
    session.add(item)
    await session.flush()
    return item


@router.patch("/entries/{item_id}")
async def patch_entry(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Entry not found")
    for k, v in payload.items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/entries/{item_id}", status_code=204)
async def delete_entry(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/entries/{item_id}/sign-employee")
async def sign_employee(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    sig = await BriefingEntryService().sign(session, item, "employee", payload.get("signer_user_id"))
    return {"entry": item, "signature": sig}


@router.post("/entries/{item_id}/sign-instructor")
async def sign_instructor(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    sig = await BriefingEntryService().sign(session, item, "instructor", payload.get("signer_user_id"))
    return {"entry": item, "signature": sig}


@router.post("/entries/{item_id}/complete")
async def complete_entry(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    try:
        return await BriefingEntryService().complete(session, item)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/entries/bulk-create")
async def bulk_create_entries(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    created = []
    for person_id in payload.get("person_ids", []):
        entry = BriefingEntry(tenant_id=tenant.id, person_id=person_id, **{k: v for k, v in payload.items() if k != "person_ids"})
        session.add(entry)
        created.append(entry)
    await session.flush()
    return {"items": created, "total": len(created)}
