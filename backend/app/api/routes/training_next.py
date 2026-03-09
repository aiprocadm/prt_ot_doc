from __future__ import annotations

from datetime import date, datetime, timezone

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import (
    Tenant,
    TrainingCertificate,
    TrainingEnrollment,
    TrainingGroup,
    TrainingModule,
    TrainingProgram,
    TrainingProtocol,
    TrainingTest,
    TrainingTestQuestion,
)
from app.modules.external_registry.services import ExternalRegistryDispatchService
from app.modules.training.services import TrainingCertificateService, TrainingEnrollmentService
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/training", tags=["training-next"])


@router.get("/programs")
async def list_programs(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(TrainingProgram).where(TrainingProgram.tenant_id == tenant.id, TrainingProgram.deleted_at.is_(None)).order_by(TrainingProgram.created_at.desc()))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/programs", status_code=status.HTTP_201_CREATED)
async def create_program(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = TrainingProgram(tenant_id=tenant.id, **payload)
    session.add(item)
    await session.flush()
    return item


@router.get("/programs/{item_id}")
async def get_program(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(TrainingProgram, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Program not found")
    return item


@router.patch("/programs/{item_id}")
async def patch_program(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await get_program(item_id, tenant, session)
    for k, v in payload.items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/programs/{item_id}", status_code=204)
async def delete_program(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await get_program(item_id, tenant, session)
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/programs/{item_id}/modules", status_code=201)
async def create_module(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    await get_program(item_id, tenant, session)
    module = TrainingModule(tenant_id=tenant.id, training_program_id=item_id, **payload)
    session.add(module)
    await session.flush()
    return module


@router.patch("/modules/{module_id}")
async def patch_module(module_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    module = await session.get(TrainingModule, module_id)
    if not module or module.tenant_id != tenant.id:
        raise HTTPException(404, "Module not found")
    for k, v in payload.items():
        setattr(module, k, v)
    await session.flush()
    return module


@router.delete("/modules/{module_id}", status_code=204)
async def delete_module(module_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    module = await session.get(TrainingModule, module_id)
    if not module or module.tenant_id != tenant.id:
        raise HTTPException(404, "Module not found")
    await session.delete(module)
    await session.flush()


@router.get("/tests")
async def list_tests(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(TrainingTest).where(TrainingTest.tenant_id == tenant.id, TrainingTest.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/tests", status_code=201)
async def create_test(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = TrainingTest(tenant_id=tenant.id, **payload)
    session.add(item)
    await session.flush()
    return item


@router.get("/tests/{item_id}")
async def get_test(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await session.get(TrainingTest, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Test not found")
    return item


@router.patch("/tests/{item_id}")
async def patch_test(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await get_test(item_id, tenant, session)
    for k, v in payload.items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/tests/{item_id}", status_code=204)
async def delete_test(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    item = await get_test(item_id, tenant, session)
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/tests/{item_id}/questions", status_code=201)
async def create_question(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    await get_test(item_id, tenant, session)
    q = TrainingTestQuestion(tenant_id=tenant.id, training_test_id=item_id, **payload)
    session.add(q)
    await session.flush()
    return q


@router.patch("/questions/{question_id}")
async def patch_question(question_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    q = await session.get(TrainingTestQuestion, question_id)
    if not q or q.tenant_id != tenant.id:
        raise HTTPException(404, "Question not found")
    for k, v in payload.items():
        setattr(q, k, v)
    await session.flush()
    return q


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(question_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    q = await session.get(TrainingTestQuestion, question_id)
    if not q or q.tenant_id != tenant.id:
        raise HTTPException(404, "Question not found")
    await session.delete(q)
    await session.flush()


@router.get("/groups")
async def list_groups(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(TrainingGroup).where(TrainingGroup.tenant_id == tenant.id, TrainingGroup.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/groups", status_code=201)
async def create_group(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    g = TrainingGroup(tenant_id=tenant.id, **payload)
    session.add(g)
    await session.flush()
    return g


@router.get("/groups/{item_id}")
async def get_group(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    g = await session.get(TrainingGroup, item_id)
    if not g or g.tenant_id != tenant.id or g.deleted_at is not None:
        raise HTTPException(404, "Group not found")
    return g


@router.patch("/groups/{item_id}")
async def patch_group(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    g = await get_group(item_id, tenant, session)
    for k, v in payload.items():
        setattr(g, k, v)
    await session.flush()
    return g


@router.delete("/groups/{item_id}", status_code=204)
async def delete_group(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    g = await get_group(item_id, tenant, session)
    g.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/groups/{item_id}/schedule")
async def schedule_group(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    g = await get_group(item_id, tenant, session)
    g.planned_start_at = datetime.fromisoformat(payload["planned_start_at"])
    g.planned_end_at = datetime.fromisoformat(payload["planned_end_at"])
    g.status = "scheduled"
    await session.flush()
    return g


@router.post("/groups/{item_id}/complete")
async def complete_group(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    g = await get_group(item_id, tenant, session)
    g.status = "completed"
    await session.flush()
    return g


@router.get("/enrollments")
async def list_enrollments(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), person_id: str | None = Query(default=None), status_f: str | None = Query(default=None, alias="status")):
    stmt = select(TrainingEnrollment).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(TrainingEnrollment.person_id == person_id)
    if status_f:
        stmt = stmt.where(TrainingEnrollment.status == status_f)
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/enrollments", status_code=201)
async def create_enrollment(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = TrainingEnrollment(tenant_id=tenant.id, assigned_at=datetime.now(tz=timezone.utc), **payload)
    session.add(e)
    await session.flush()
    return e


@router.get("/enrollments/{item_id}")
async def get_enrollment(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await session.get(TrainingEnrollment, item_id)
    if not e or e.tenant_id != tenant.id or e.deleted_at is not None:
        raise HTTPException(404, "Enrollment not found")
    return e


@router.patch("/enrollments/{item_id}")
async def patch_enrollment(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await get_enrollment(item_id, tenant, session)
    for k, v in payload.items():
        setattr(e, k, v)
    await session.flush()
    return e


@router.delete("/enrollments/{item_id}", status_code=204)
async def delete_enrollment(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await get_enrollment(item_id, tenant, session)
    e.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/enrollments/{item_id}/start")
async def start_enrollment(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await get_enrollment(item_id, tenant, session)
    return await TrainingEnrollmentService().start(session, e)


@router.post("/enrollments/{item_id}/submit-attempt")
async def submit_attempt(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await get_enrollment(item_id, tenant, session)
    attempt = await TrainingEnrollmentService().submit_attempt(session, e, payload)
    return {"enrollment": e, "attempt": attempt}


@router.post("/enrollments/{item_id}/mark-passed")
async def mark_passed(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await get_enrollment(item_id, tenant, session)
    e.status = "passed"
    e.completed_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return e


@router.post("/enrollments/{item_id}/mark-failed")
async def mark_failed(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    e = await get_enrollment(item_id, tenant, session)
    e.status = "failed"
    await session.flush()
    return e


@router.get("/protocols")
async def list_protocols(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(TrainingProtocol).where(TrainingProtocol.tenant_id == tenant.id, TrainingProtocol.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/protocols", status_code=201)
async def create_protocol(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    p = TrainingProtocol(tenant_id=tenant.id, protocol_date=date.today(), **payload)
    session.add(p)
    await session.flush()
    return p


@router.get("/protocols/{item_id}")
async def get_protocol(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    p = await session.get(TrainingProtocol, item_id)
    if not p or p.tenant_id != tenant.id or p.deleted_at is not None:
        raise HTTPException(404, "Protocol not found")
    return p


@router.patch("/protocols/{item_id}")
async def patch_protocol(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    p = await get_protocol(item_id, tenant, session)
    for k, v in payload.items():
        setattr(p, k, v)
    await session.flush()
    return p


@router.delete("/protocols/{item_id}", status_code=204)
async def delete_protocol(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    p = await get_protocol(item_id, tenant, session)
    p.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/protocols/{item_id}/issue")
async def issue_protocol(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    p = await get_protocol(item_id, tenant, session)
    p.status = "issued"
    await session.flush()
    return p


@router.get("/certificates")
async def list_certificates(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(TrainingCertificate).where(TrainingCertificate.tenant_id == tenant.id, TrainingCertificate.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/certificates", status_code=201)
async def create_certificate(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    if not payload.get("code"):
        payload["code"] = await TrainingCertificateService().next_code(session, tenant.id)
    c = TrainingCertificate(tenant_id=tenant.id, issued_at=date.today(), status="active", **payload)
    session.add(c)
    await session.flush()
    return c


@router.get("/certificates/{item_id}")
async def get_certificate(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    c = await session.get(TrainingCertificate, item_id)
    if not c or c.tenant_id != tenant.id or c.deleted_at is not None:
        raise HTTPException(404, "Certificate not found")
    return c


@router.patch("/certificates/{item_id}")
async def patch_certificate(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    c = await get_certificate(item_id, tenant, session)
    for k, v in payload.items():
        setattr(c, k, v)
    await session.flush()
    return c


@router.delete("/certificates/{item_id}", status_code=204)
async def delete_certificate(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    c = await get_certificate(item_id, tenant, session)
    c.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/certificates/{item_id}/revoke")
async def revoke_certificate(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    c = await get_certificate(item_id, tenant, session)
    c.status = "revoked"
    await session.flush()
    return c


@router.post("/certificates/{item_id}/send-registry")
async def send_certificate_registry(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    await get_certificate(item_id, tenant, session)
    service = ExternalRegistryDispatchService()
    job = await service.enqueue(session, tenant.id, "certificate", item_id, "frdo")
    return await service.dispatch(session, job)


@router.post("/protocols/{item_id}/send-registry")
async def send_protocol_registry(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    await get_protocol(item_id, tenant, session)
    service = ExternalRegistryDispatchService()
    job = await service.enqueue(session, tenant.id, "protocol", item_id, "eisot")
    return await service.dispatch(session, job)
