from __future__ import annotations

import pytest
from app.models.models import (
    RoleEnum,
    TrainingEnrollment,
    TrainingGroup,
    TrainingModule,
    TrainingProgram,
)


@pytest.mark.anyio
async def test_training_teacher_and_runtime_flow(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(session=session, tenant=tenant)
        person = await data_factory.create_person(session=session, tenant=tenant, company=company)
        program = TrainingProgram(tenant_id=tenant.id, code="prog-1", title="LMS", category="ot", kind="course", status="active")
        session.add(program)
        await session.flush()
        group = TrainingGroup(tenant_id=tenant.id, code="grp-1", training_program_id=program.id, title="Group", teacher_user_id="teacher-1", status="scheduled")
        module = TrainingModule(tenant_id=tenant.id, training_program_id=program.id, title="Module", module_order=1, content_type="document")
        session.add_all([group, module])
        await session.flush()
        enrollment = TrainingEnrollment(tenant_id=tenant.id, training_group_id=group.id, training_program_id=program.id, person_id=person.id, assignment_source="manual", status="assigned")
        session.add(enrollment)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    lesson = await async_client.post(f"/api/v1/training/modules/{module.id}/lessons", json={"title": "Lesson", "lesson_order": 1}, headers={**headers, "X-Tenant": "test"})
    assert lesson.status_code == 201

    progress = await async_client.post(f"/api/v1/training/enrollments/{enrollment.id}/progress", json={"completed_lesson_ids": [lesson.json()["id"]], "provider": "xapi", "event": "progressed"}, headers={**headers, "X-Tenant": "test"})
    assert progress.status_code == 200
    assert float(progress.json()["progress_percent"]) == 100

    runtime = await async_client.post(f"/api/v1/training/enrollments/{enrollment.id}/runtime-results", json={"content_format": "scorm", "session_ref": "sess-1", "score": 92, "passed": True}, headers={**headers, "X-Tenant": "test"})
    assert runtime.status_code == 200
    assert runtime.json()["enrollment"]["completion_status"] == "completed"

    teacher = await async_client.get("/api/v1/training/teacher/dashboard", headers={**headers, "X-Tenant": "test"})
    assert teacher.status_code == 200
    assert teacher.json()["enrollments_total"] == 1

    learner = await async_client.get(f"/api/v1/training/learner/dashboard?person_id={person.id}", headers={**headers, "X-Tenant": "test"})
    assert learner.status_code == 200
    assert learner.json()["completed_total"] == 1

    program_detail = await async_client.get(f"/api/v1/training/programs/{program.id}/detail", headers={**headers, "X-Tenant": "test"})
    assert program_detail.status_code == 200
    assert program_detail.json()["lessons_total"] == 1

    enrollment_detail = await async_client.get(f"/api/v1/training/enrollments/{enrollment.id}/detail", headers={**headers, "X-Tenant": "test"})
    assert enrollment_detail.status_code == 200
    assert enrollment_detail.json()["completion"]["status"] == "completed"

    analytics = await async_client.get("/api/v1/training/analytics/overview", headers={**headers, "X-Tenant": "test"})
    assert analytics.status_code == 200
    assert analytics.json()["completed_total"] == 1
    assert analytics.json()["material_types"]["document"] == 1

    retake = await async_client.post(f"/api/v1/training/enrollments/{enrollment.id}/retake", json={"reason": "manual review"}, headers={**headers, "X-Tenant": "test"})
    assert retake.status_code == 200
    assert retake.json()["completion_status"] == "retake_assigned"
