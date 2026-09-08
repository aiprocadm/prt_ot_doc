"""compliance.deadlines.tick (BIZ-54-57 срез-116): ночная пересборка снимка
контрольных сроков и правило «уволенный не в счёт» для него.

Снимок ``compliance_deadline`` строится из удостоверений обучения и до среза
пересобирался ТОЛЬКО кнопкой ``POST /compliance/deadlines/recompute``. Между
нажатиями он врал в обе стороны: продлённое удостоверение оставалось
«просроченным» в календаре и карточке сотрудника, а новое не появлялось вовсе.
Кнопку жмёт человек, а сроки идут сами.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.master_data import EmploymentStatus
from app.models.models import ComplianceDeadline, TrainingCertificate
from app.services.celery_app import celery_app

pytestmark = pytest.mark.anyio


def test_расписание_знает_ночную_пересборку_снимка() -> None:
    entry = celery_app.conf.beat_schedule["compliance-deadlines-daily"]
    assert entry["task"] == "compliance.deadlines.tick"
    assert "compliance.deadlines.tick" in celery_app.tasks


async def test_тик_собирает_снимок_без_нажатия_кнопки(sessionmaker, data_factory) -> None:
    """Новое удостоверение попадает в снимок само — раньше ждало кнопки."""

    from app.tasks._core import _compliance_deadlines_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Учился", session=session
        )
        session.add(
            TrainingCertificate(
                tenant_id=str(tenant.id),
                person_id=person.id,
                code="УД-116",
                issued_at=date.today() - timedelta(days=400),
                valid_until=date.today() - timedelta(days=10),
            )
        )
        await session.commit()

    total = await _compliance_deadlines_tick()
    assert total >= 1

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(ComplianceDeadline).where(
                        ComplianceDeadline.tenant_id == str(tenant.id),
                        ComplianceDeadline.person_id == person.id,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].entity_type == "training_certificate"
    assert rows[0].status == "overdue"


async def test_повторный_прогон_не_плодит_строк(sessionmaker, data_factory) -> None:
    """Пересборка — «удалить и записать заново»: повтор безопасен."""

    from app.tasks._core import _compliance_deadlines_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Повтор", session=session
        )
        session.add(
            TrainingCertificate(
                tenant_id=str(tenant.id),
                person_id=person.id,
                code="УД-116-2",
                issued_at=date.today(),
                valid_until=date.today() + timedelta(days=300),
            )
        )
        await session.commit()

    await _compliance_deadlines_tick()
    await _compliance_deadlines_tick()

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(ComplianceDeadline).where(
                        ComplianceDeadline.tenant_id == str(tenant.id),
                        ComplianceDeadline.person_id == person.id,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].status == "upcoming"


async def test_срок_уволенного_в_календарь_не_попадает(
    sessionmaker, data_factory, async_client, make_auth_headers
) -> None:
    """«Уволенный не в счёт» (срез-116) — последний источник календаря без правила.

    Снимок хранит ``person_id``, значит он про человека: просроченное
    удостоверение уволенного «горело» в общем календаре и в Центре внимания,
    хотя обязательства перед ним нет.
    """

    from app.tasks._core import _compliance_deadlines_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        here = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Работает116", session=session
        )
        gone = await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Уволен116",
            session=session,
            employment_status=EmploymentStatus.TERMINATED,
        )
        for person in (here, gone):
            session.add(
                TrainingCertificate(
                    tenant_id=str(tenant.id),
                    person_id=person.id,
                    code=f"УД-{person.last_name}",
                    issued_at=date.today() - timedelta(days=400),
                    valid_until=date.today() - timedelta(days=5),
                )
            )
        await session.commit()

    await _compliance_deadlines_tick()

    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/calendar/events",
        params={"sources": "compliance_deadline"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    person_ids = {item.get("person_id") for item in body["items"]}
    assert here.id in person_ids
    assert gone.id not in person_ids
