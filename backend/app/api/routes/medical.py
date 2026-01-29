"""Medical requirement endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import Person, Tenant
from app.schemas.medical import MedicalRequirementCreate
from app.schemas.task import TaskRead
from app.services.obligations import create_medical_task

router = APIRouter(tags=["medical"])

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


MedicalAccess = Depends(
    abac(_tenant_resource_id, required_roles=["admin", "owner", "hr"], action="manage medical")
)


@router.post("/medical/requirements", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_medical_requirement(
    payload: MedicalRequirementCreate,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = MedicalAccess,
) -> TaskRead:
    stmt = select(Person).where(
        Person.id == payload.person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")

    task = await create_medical_task(
        session,
        tenant_id=str(tenant.id),
        person_id=person.id,
        due_date=payload.due_date,
        actor_id=getattr(access.user, "id", None),
    )
    if payload.notes:
        task.description = (task.description or "") + f"\n{payload.notes}"
    await session.commit()
    await session.refresh(task)
    return TaskRead.model_validate(task)
