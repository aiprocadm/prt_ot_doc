"""Мера тарифа: сколько работников арендатор ведёт (BIZ-54-57 срез-121).

ЗАЧЕМ. Счётчик считал ``employment_status == ACTIVE`` и расходился с самим
продуктом: у человека в отпуске не пропадают ни медосмотр, ни СИЗ, ни
обучение — платформа ведёт его наравне с остальными, а в счёт он не попадал.
Побочно это подсказывало способ платить меньше: перевести людей в отпуск.
"""

from __future__ import annotations

import pytest

from app.models.master_data import EmploymentStatus


@pytest.mark.asyncio
async def test_считаются_все_кто_числится(sessionmaker, data_factory) -> None:
    """Отпуск и отстранение — это те же обязательства, а увольнение — история."""

    from app.services.billing import count_employed_workers

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="ООО Мера", session=session)
        for last_name, status in (
            ("Активов", EmploymentStatus.ACTIVE),
            ("Отпускной", EmploymentStatus.ON_LEAVE),
            ("Отстранённый", EmploymentStatus.SUSPENDED),
            ("Уволенный", EmploymentStatus.TERMINATED),
        ):
            await data_factory.create_person(
                tenant=tenant,
                company=company,
                first_name="Иван",
                last_name=last_name,
                employment_status=status,
                session=session,
            )
        await session.flush()

        assert await count_employed_workers(session, str(tenant.id)) == 3


@pytest.mark.asyncio
async def test_удалённая_запись_не_считается(sessionmaker, data_factory) -> None:
    """Удалённый работник — не работник, даже если статус остался «активен»."""

    from datetime import datetime, timezone

    from app.services.billing import count_employed_workers

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Мера 2", session=session
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Пётр",
            last_name="Удалённый",
            employment_status=EmploymentStatus.ACTIVE,
            session=session,
        )
        person.deleted_at = datetime.now(tz=timezone.utc)
        await session.flush()

        assert await count_employed_workers(session, str(tenant.id)) == 0


def test_задача_тарифа_зарегистрирована() -> None:
    from app.services.celery_app import celery_app
    from app.tasks import _core  # noqa: F401  -- регистрирует задачи

    assert "billing.recompute_active_workers" in celery_app.tasks


async def test_у_работников_нет_выдуманного_процента(
    async_client, make_auth_headers, sessionmaker
) -> None:
    """Срез-121: `max_users` ограничивает ВХОДЫ, а не работников.

    Деление одного на другое давало бессмысленный процент: у арендатора со
    100 сотрудниками и лимитом в 20 учётных записей на экране горело «500%».
    Нет лимита — нет процента; так же продукт поступает везде, где мерить
    нечем.
    """

    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.models import (
        BillingPlan,
        BillingSubscription,
        BillingSubscriptionStatus,
        Tenant,
    )

    headers = await make_auth_headers()
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        plan = BillingPlan(
            code="meter-121",
            name="Тариф со счётом входов",
            limits={"max_users": 20},
            features={},
        )
        session.add(plan)
        await session.flush()
        session.add(
            BillingSubscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status=BillingSubscriptionStatus.ACTIVE,
                period_start=datetime.now(tz=timezone.utc),
                period_end=datetime.now(tz=timezone.utc) + timedelta(days=30),
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/billing/usage", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "active_workers_count" in body["usage"]
    assert body["percentages"]["active_workers_count"] is None
