from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import rbac
from app.models.models import (
    Tenant,
    TrainingCertificate,
    TrainingEnrollment,
    TrainingGroup,
    TrainingLesson,
    TrainingModule,
    TrainingProgram,
    TrainingProtocol,
    TrainingTest,
    TrainingTestQuestion,
)
from app.modules.external_registry.services import ExternalRegistryDispatchService
from app.modules.rbac_abac import require_permission
from app.modules.training.services import TrainingCertificateService, TrainingEnrollmentService

router = APIRouter(prefix="/training", tags=["training-next"], dependencies=[Depends(rbac())])

_PermReadDep = Depends(require_permission("trainings.read"))
_PermCreateDep = Depends(require_permission("trainings.create"))
_PermWriteDep = Depends(require_permission("trainings.update"))

# System-managed fields that callers must never be able to override via raw dict payloads.
_PROTECTED_FIELDS: frozenset[str] = frozenset({
    "id", "tenant_id", "created_at", "updated_at", "deleted_at",
    "created_by", "updated_by", "hash", "version",
})


def _safe(payload: dict) -> dict:
    """Strip protected system fields from an incoming dict payload."""
    return {k: v for k, v in payload.items() if k not in _PROTECTED_FIELDS}

@router.get("/programs")
async def list_programs(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    rows = (await session.execute(select(TrainingProgram).where(TrainingProgram.tenant_id == tenant.id, TrainingProgram.deleted_at.is_(None)).order_by(TrainingProgram.created_at.desc()))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/programs", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "training_program")
async def create_program(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    item = TrainingProgram(tenant_id=tenant.id, **_safe(payload))
    session.add(item)
    await session.flush()
    return item


@router.get("/programs/{item_id}")
async def get_program(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    item = await session.get(TrainingProgram, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Program not found")
    return item


@router.patch("/programs/{item_id}")
@audit_operation("update", "training_program")
async def patch_program(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    item = await get_program(item_id, tenant, session)
    for k, v in _safe(payload).items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/programs/{item_id}", status_code=204)
@audit_operation("delete", "training_program")
async def delete_program(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    item = await get_program(item_id, tenant, session)
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/programs/{item_id}/modules", status_code=201)
@audit_operation("create", "training_module")
async def create_module(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    await get_program(item_id, tenant, session)
    module = TrainingModule(tenant_id=tenant.id, training_program_id=item_id, **_safe(payload))
    session.add(module)
    await session.flush()
    return module


@router.patch("/modules/{module_id}")
@audit_operation("update", "training_module")
async def patch_module(module_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    module = await session.get(TrainingModule, module_id)
    if not module or module.tenant_id != tenant.id:
        raise HTTPException(404, "Module not found")
    for k, v in _safe(payload).items():
        setattr(module, k, v)
    await session.flush()
    return module


@router.delete("/modules/{module_id}", status_code=204)
@audit_operation("delete", "training_module")
async def delete_module(module_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    module = await session.get(TrainingModule, module_id)
    if not module or module.tenant_id != tenant.id:
        raise HTTPException(404, "Module not found")
    await session.delete(module)
    await session.flush()


@router.get("/tests")
async def list_tests(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    rows = (await session.execute(select(TrainingTest).where(TrainingTest.tenant_id == tenant.id, TrainingTest.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/tests", status_code=201)
@audit_operation("create", "training_test")
async def create_test(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    item = TrainingTest(tenant_id=tenant.id, **_safe(payload))
    session.add(item)
    await session.flush()
    return item


@router.get("/tests/{item_id}")
async def get_test(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    item = await session.get(TrainingTest, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Test not found")
    return item


@router.patch("/tests/{item_id}")
@audit_operation("update", "training_test")
async def patch_test(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    item = await get_test(item_id, tenant, session)
    for k, v in _safe(payload).items():
        setattr(item, k, v)
    await session.flush()
    return item


@router.delete("/tests/{item_id}", status_code=204)
@audit_operation("delete", "training_test")
async def delete_test(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    item = await get_test(item_id, tenant, session)
    item.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/tests/{item_id}/questions", status_code=201)
@audit_operation("create", "training_question")
async def create_question(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    await get_test(item_id, tenant, session)
    q = TrainingTestQuestion(tenant_id=tenant.id, training_test_id=item_id, **_safe(payload))
    session.add(q)
    await session.flush()
    return q


@router.patch("/questions/{question_id}")
@audit_operation("update", "training_question")
async def patch_question(question_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    q = await session.get(TrainingTestQuestion, question_id)
    if not q or q.tenant_id != tenant.id:
        raise HTTPException(404, "Question not found")
    for k, v in _safe(payload).items():
        setattr(q, k, v)
    await session.flush()
    return q


@router.delete("/questions/{question_id}", status_code=204)
@audit_operation("delete", "training_question")
async def delete_question(question_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    q = await session.get(TrainingTestQuestion, question_id)
    if not q or q.tenant_id != tenant.id:
        raise HTTPException(404, "Question not found")
    await session.delete(q)
    await session.flush()


@router.get("/groups")
async def list_groups(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    rows = (await session.execute(select(TrainingGroup).where(TrainingGroup.tenant_id == tenant.id, TrainingGroup.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/groups", status_code=201)
@audit_operation("create", "training_group")
async def create_group(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    g = TrainingGroup(tenant_id=tenant.id, **_safe(payload))
    session.add(g)
    await session.flush()
    return g


@router.get("/groups/{item_id}")
async def get_group(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    g = await session.get(TrainingGroup, item_id)
    if not g or g.tenant_id != tenant.id or g.deleted_at is not None:
        raise HTTPException(404, "Group not found")
    return g


@router.patch("/groups/{item_id}")
@audit_operation("update", "training_group")
async def patch_group(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    g = await get_group(item_id, tenant, session)
    for k, v in _safe(payload).items():
        setattr(g, k, v)
    await session.flush()
    return g


@router.delete("/groups/{item_id}", status_code=204)
@audit_operation("delete", "training_group")
async def delete_group(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    g = await get_group(item_id, tenant, session)
    g.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/groups/{item_id}/schedule")
@audit_operation("schedule", "training_group")
async def schedule_group(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    g = await get_group(item_id, tenant, session)
    g.planned_start_at = datetime.fromisoformat(payload["planned_start_at"])
    g.planned_end_at = datetime.fromisoformat(payload["planned_end_at"])
    g.status = "scheduled"
    await session.flush()
    return g


@router.post("/groups/{item_id}/complete")
@audit_operation("complete", "training_group")
async def complete_group(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    g = await get_group(item_id, tenant, session)
    g.status = "completed"
    await session.flush()
    return g


@router.get("/enrollments")
async def list_enrollments(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), person_id: str | None = Query(default=None), status_f: str | None = Query(default=None, alias="status"), __: Any = _PermReadDep):
    stmt = select(TrainingEnrollment).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(TrainingEnrollment.person_id == person_id)
    if status_f:
        stmt = stmt.where(TrainingEnrollment.status == status_f)
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/enrollments", status_code=201)
@audit_operation("create", "training_enrollment")
async def create_enrollment(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    e = TrainingEnrollment(tenant_id=tenant.id, assigned_at=datetime.now(tz=timezone.utc), **_safe(payload))
    session.add(e)
    await session.flush()
    return e


@router.get("/enrollments/{item_id}")
async def get_enrollment(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    e = await session.get(TrainingEnrollment, item_id)
    if not e or e.tenant_id != tenant.id or e.deleted_at is not None:
        raise HTTPException(404, "Enrollment not found")
    return e


@router.patch("/enrollments/{item_id}")
@audit_operation("update", "training_enrollment")
async def patch_enrollment(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    e = await get_enrollment(item_id, tenant, session)
    for k, v in _safe(payload).items():
        setattr(e, k, v)
    await session.flush()
    return e


@router.delete("/enrollments/{item_id}", status_code=204)
@audit_operation("delete", "training_enrollment")
async def delete_enrollment(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    e = await get_enrollment(item_id, tenant, session)
    e.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/enrollments/{item_id}/start")
@audit_operation("start", "training_enrollment")
async def start_enrollment(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    e = await get_enrollment(item_id, tenant, session)
    return await TrainingEnrollmentService().start(session, e)


@router.post("/enrollments/{item_id}/submit-attempt")
@audit_operation("submit_attempt", "training_enrollment")
async def submit_attempt(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    e = await get_enrollment(item_id, tenant, session)
    attempt = await TrainingEnrollmentService().submit_attempt(session, e, payload)
    return {"enrollment": e, "attempt": attempt}


@router.post("/enrollments/{item_id}/mark-passed")
@audit_operation("mark_passed", "training_enrollment")
async def mark_passed(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    e = await get_enrollment(item_id, tenant, session)
    e.status = "passed"
    e.completed_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return e


@router.post("/enrollments/{item_id}/mark-failed")
@audit_operation("mark_failed", "training_enrollment")
async def mark_failed(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    e = await get_enrollment(item_id, tenant, session)
    e.status = "failed"
    await session.flush()
    return e


@router.get("/protocols")
async def list_protocols(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    rows = (await session.execute(select(TrainingProtocol).where(TrainingProtocol.tenant_id == tenant.id, TrainingProtocol.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/protocols", status_code=201)
@audit_operation("create", "training_protocol")
async def create_protocol(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    p = TrainingProtocol(tenant_id=tenant.id, protocol_date=date.today(), **_safe(payload))
    session.add(p)
    await session.flush()
    return p


@router.get("/protocols/{item_id}")
async def get_protocol(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    p = await session.get(TrainingProtocol, item_id)
    if not p or p.tenant_id != tenant.id or p.deleted_at is not None:
        raise HTTPException(404, "Protocol not found")
    return p


@router.patch("/protocols/{item_id}")
@audit_operation("update", "training_protocol")
async def patch_protocol(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    p = await get_protocol(item_id, tenant, session)
    for k, v in _safe(payload).items():
        setattr(p, k, v)
    await session.flush()
    return p


@router.delete("/protocols/{item_id}", status_code=204)
@audit_operation("delete", "training_protocol")
async def delete_protocol(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    p = await get_protocol(item_id, tenant, session)
    p.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/protocols/{item_id}/issue")
@audit_operation("issue", "training_protocol")
async def issue_protocol(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    p = await get_protocol(item_id, tenant, session)
    p.status = "issued"
    await session.flush()
    return p


@router.get("/certificates")
async def list_certificates(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    rows = (await session.execute(select(TrainingCertificate).where(TrainingCertificate.tenant_id == tenant.id, TrainingCertificate.deleted_at.is_(None)))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/certificates:create", status_code=201)
@audit_operation("create", "training_certificate")
async def create_certificate(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    if not payload.get("code"):
        payload["code"] = await TrainingCertificateService().next_code(session, tenant.id)
    c = TrainingCertificate(tenant_id=tenant.id, issued_at=date.today(), status="active", **_safe(payload))
    session.add(c)
    await session.flush()
    return c


@router.get("/certificates/{item_id}")
async def get_certificate(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    c = await session.get(TrainingCertificate, item_id)
    if not c or c.tenant_id != tenant.id or c.deleted_at is not None:
        raise HTTPException(404, "Certificate not found")
    return c


@router.patch("/certificates/{item_id}")
@audit_operation("update", "training_certificate")
async def patch_certificate(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    c = await get_certificate(item_id, tenant, session)
    for k, v in _safe(payload).items():
        setattr(c, k, v)
    await session.flush()
    return c


@router.delete("/certificates/{item_id}", status_code=204)
@audit_operation("delete", "training_certificate")
async def delete_certificate(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    c = await get_certificate(item_id, tenant, session)
    c.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


@router.post("/certificates/{item_id}/revoke")
@audit_operation("revoke", "training_certificate")
async def revoke_certificate(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    c = await get_certificate(item_id, tenant, session)
    c.status = "revoked"
    await session.flush()
    return c


@router.post("/certificates/{item_id}/send-registry")
@audit_operation("send_registry", "training_certificate")
async def send_certificate_registry(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    await get_certificate(item_id, tenant, session)
    service = ExternalRegistryDispatchService()
    job = await service.enqueue(session, tenant.id, "certificate", item_id, "frdo")
    return await service.dispatch(session, job)


@router.post("/protocols/{item_id}/send-registry")
@audit_operation("send_registry", "training_protocol")
async def send_protocol_registry(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    await get_protocol(item_id, tenant, session)
    service = ExternalRegistryDispatchService()
    job = await service.enqueue(session, tenant.id, "protocol", item_id, "eisot")
    return await service.dispatch(session, job)


@router.post("/modules/{module_id}/lessons", status_code=201)
@audit_operation("create", "training_lesson")
async def create_lesson(module_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermCreateDep):
    module = await session.get(TrainingModule, module_id)
    if not module or module.tenant_id != tenant.id:
        raise HTTPException(404, "Module not found")
    lesson = TrainingLesson(tenant_id=tenant.id, training_module_id=module_id, **_safe(payload))
    session.add(lesson)
    await session.flush()
    return lesson


@router.get("/programs/{item_id}/detail")
async def get_program_detail(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    program = await get_program(item_id, tenant, session)
    modules = (
        await session.execute(
            select(TrainingModule).where(
                TrainingModule.tenant_id == tenant.id,
                TrainingModule.training_program_id == program.id,
            ).order_by(TrainingModule.module_order.asc(), TrainingModule.created_at.asc())
        )
    ).scalars().all()
    module_ids = [module.id for module in modules]
    lessons = (
        await session.execute(
            select(TrainingLesson).where(
                TrainingLesson.tenant_id == tenant.id,
                TrainingLesson.training_module_id.in_(module_ids or ["__none__"]),
            ).order_by(TrainingLesson.lesson_order.asc(), TrainingLesson.created_at.asc())
        )
    ).scalars().all()
    lessons_by_module: dict[str, list[TrainingLesson]] = {}
    for lesson in lessons:
        lessons_by_module.setdefault(lesson.training_module_id, []).append(lesson)
    return {
        "program": program,
        "modules": [
            {
                "module": module,
                "lessons": lessons_by_module.get(module.id, []),
                "materials": module.materials_json or {},
            }
            for module in modules
        ],
        "lessons_total": len(lessons),
    }


@router.get("/enrollments/{item_id}/detail")
async def get_enrollment_detail(item_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    enrollment = await get_enrollment(item_id, tenant, session)
    program = await session.get(TrainingProgram, enrollment.training_program_id)
    program_detail = await get_program_detail(enrollment.training_program_id, tenant, session)
    runtime = enrollment.external_runtime_state or {}
    modules = program_detail["modules"]
    return {
        "enrollment": enrollment,
        "program": program,
        "modules": modules,
        "completion": {
            "status": enrollment.completion_status,
            "progress_percent": enrollment.progress_percent,
            "confirmed_at": enrollment.completion_confirmed_at,
            "certificate_id": enrollment.certificate_id,
            "runtime": runtime,
        },
    }


@router.get("/teacher/dashboard")
async def teacher_dashboard(
    teacher_user_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermReadDep,
):
    group_stmt = select(TrainingGroup).where(TrainingGroup.tenant_id == tenant.id, TrainingGroup.deleted_at.is_(None))
    if teacher_user_id:
        group_stmt = group_stmt.where(TrainingGroup.teacher_user_id == teacher_user_id)
    groups = (await session.execute(group_stmt)).scalars().all()
    group_ids = [group.id for group in groups]
    enrollment_total = int((await session.execute(select(func.count()).select_from(TrainingEnrollment).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.training_group_id.in_(group_ids or ["__none__"]), TrainingEnrollment.deleted_at.is_(None)))).scalar_one())
    completed_total = int((await session.execute(select(func.count()).select_from(TrainingEnrollment).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.training_group_id.in_(group_ids or ["__none__"]), TrainingEnrollment.completion_status.in_(["completed", "confirmed"]), TrainingEnrollment.deleted_at.is_(None)))).scalar_one())
    avg_progress = float((await session.execute(select(func.avg(TrainingEnrollment.progress_percent)).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.training_group_id.in_(group_ids or ["__none__"]), TrainingEnrollment.deleted_at.is_(None)))).scalar() or 0)
    return {
        "groups_total": len(groups),
        "enrollments_total": enrollment_total,
        "completed_total": completed_total,
        "average_progress_percent": round(avg_progress, 2),
        "groups": groups,
        "items": [
            {
                "group_id": group.id,
                "title": group.title,
                "status": group.status,
                "planned_start_at": group.planned_start_at,
                "planned_end_at": group.planned_end_at,
            }
            for group in groups
        ],
    }


@router.get("/learner/dashboard")
async def learner_dashboard(
    person_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _PermReadDep,
):
    stmt = select(TrainingEnrollment).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.deleted_at.is_(None))
    if person_id != "me":
        stmt = stmt.where(TrainingEnrollment.person_id == person_id)
    enrollments = (await session.execute(stmt.order_by(TrainingEnrollment.updated_at.desc()))).scalars().all()
    completed = sum(1 for item in enrollments if item.completion_status in {"completed", "confirmed"})
    overdue = sum(1 for item in enrollments if item.due_at and item.due_at < datetime.now(tz=timezone.utc) and item.completion_status not in {"completed", "confirmed"})
    return {
        "person_id": person_id,
        "assigned_total": len(enrollments),
        "completed_total": completed,
        "overdue_total": overdue,
        "items": enrollments,
        "next_due_at": min((item.due_at for item in enrollments if item.due_at), default=None),
    }


@router.post("/enrollments/{item_id}/progress")
@audit_operation("update_progress", "training_enrollment")
async def update_enrollment_progress(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    enrollment = await get_enrollment(item_id, tenant, session)
    service = TrainingEnrollmentService()
    updated = await service.update_progress(
        session,
        enrollment,
        completed_lesson_ids=payload.get("completed_lesson_ids") or [],
        progress_percent=payload.get("progress_percent"),
        runtime_state={
            "provider": payload.get("provider"),
            "session_ref": payload.get("session_ref"),
            "content_format": payload.get("content_format"),
            "last_event": payload.get("event"),
            "proctoring": payload.get("proctoring"),
        },
    )
    return updated


@router.post("/enrollments/{item_id}/complete")
@audit_operation("confirm_completion", "training_enrollment")
async def confirm_enrollment_completion(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    enrollment = await get_enrollment(item_id, tenant, session)
    updated = await TrainingEnrollmentService().confirm_completion(
        session,
        enrollment,
        confirmed_by=payload.get("confirmed_by"),
        payload=payload,
    )
    return updated


@router.post("/enrollments/{item_id}/retake")
@audit_operation("assign_retake", "training_enrollment")
async def assign_enrollment_retake(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    enrollment = await get_enrollment(item_id, tenant, session)
    updated = await TrainingEnrollmentService().prepare_retake(
        session,
        enrollment,
        reason=payload.get("reason"),
    )
    return updated


@router.post("/enrollments/{item_id}/runtime-results")
@audit_operation("ingest_runtime_result", "training_enrollment")
async def ingest_runtime_result(item_id: str, payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    enrollment = await get_enrollment(item_id, tenant, session)
    attempt = await TrainingEnrollmentService().submit_attempt(
        session,
        enrollment,
        {"score": payload.get("score", 0), "passed": payload.get("passed", False), "raw": payload},
        source_type=payload.get("source_type", payload.get("content_format", "scorm")),
        external_session_ref=payload.get("session_ref"),
        provider_payload=payload,
    )
    return {"enrollment": enrollment, "attempt": attempt}


@router.get("/analytics/overview")
async def training_analytics_overview(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermReadDep):
    return await TrainingEnrollmentService().build_analytics_overview(session, tenant_id=tenant.id)
