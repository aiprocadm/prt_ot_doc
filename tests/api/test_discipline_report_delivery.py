"""Доставка отчёта о состоянии по дисциплинам (Доп. №1 разд. 57.4, срез-51).

Отчёт среза-50 лежал в базе и ждал, пока директор сам зайдёт на дашборд.
«Авто-отчёт для клиента» — это когда отчёт сам находит читателя. Здесь
закрепляется:

- новый отчёт уходит уведомлением владельцу, администратору и руководителю
  службы ОТ — и только им (HR, рабочий, выключенный владелец — мимо);
- текст уведомления — сводка отчёта, ссылка ведёт на дашборд;
- получатель видит его у себя в списке уведомлений;
- повторный запуск за тот же день не шлёт ничего второй раз;
- «стало хуже» уходит с приоритетом выше.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationChannelSettings,
    NotificationPriority,
    NotificationType,
)
from app.services.discipline_report import run_discipline_report
from app.services.discipline_report_delivery import REPORT_DEEPLINK
from tests.api.test_discipline_status_report import _seed

RUN = "/api/v1/analytics/discipline-reports/run"


async def _people(sessionmaker, data_factory) -> dict[str, str]:
    """Владелец, руководитель ОТ, HR, рабочий и выключенный владелец."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        users = {
            "owner": await data_factory.create_user(
                tenant=tenant, role=RoleEnum.OWNER, email="owner-dr@example.com", session=session
            ),
            "lead": await data_factory.create_user(
                tenant=tenant,
                role=RoleEnum.OT_PB_LEAD,
                email="lead-dr@example.com",
                session=session,
            ),
            "hr": await data_factory.create_user(
                tenant=tenant, role=RoleEnum.HR, email="hr-dr@example.com", session=session
            ),
            "worker": await data_factory.create_user(
                tenant=tenant, role=RoleEnum.WORKER, email="worker-dr@example.com", session=session
            ),
            "gone": await data_factory.create_user(
                tenant=tenant,
                role=RoleEnum.OWNER,
                email="gone-dr@example.com",
                is_active=False,
                session=session,
            ),
        }
        await session.commit()
        return {key: str(user.id) for key, user in users.items()}


async def _report_notifications(sessionmaker) -> list[Notification]:
    async with sessionmaker() as session:
        return list(
            (
                await session.execute(
                    select(Notification).where(
                        Notification.type == NotificationType.DISCIPLINE_REPORT,
                        Notification.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_новый_отчёт_уходит_ответственным_и_только_им(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    people = await _people(sessionmaker, data_factory)
    await _seed(sessionmaker, data_factory)
    admin_headers = await make_auth_headers(RoleEnum.ADMIN)
    owner_headers = await make_auth_headers(RoleEnum.OWNER, email="owner-dr@example.com")

    resp = await async_client.post(RUN, headers=admin_headers)

    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["created"] is True
    # владелец, руководитель ОТ и сам администратор — трое
    assert body["notified"] == 3
    assert body["summary"] == "Отчёт собран, уведомление ушло 3 получателям"

    sent = await _report_notifications(sessionmaker)
    recipients = {n.user_id for n in sent}
    assert people["owner"] in recipients
    assert people["lead"] in recipients
    assert len(recipients) == 3, "третий — администратор, нажавший кнопку"
    for key in ("hr", "worker", "gone"):
        assert people[key] not in recipients, key

    report = body["report"]
    for n in sent:
        assert n.channel == NotificationChannel.INAPP
        assert n.priority == NotificationPriority.MEDIUM, "первый отчёт — сравнивать не с чем"
        assert n.title == f"Отчёт о состоянии по дисциплинам за {date.today().strftime('%d.%m.%Y')}"
        # текст — сводка отчёта, а не второй пересказ
        assert n.body == report["summary"]
        assert n.payload["deeplink"] == REPORT_DEEPLINK
        assert n.payload["entity_id"] == report["id"]
        assert n.payload["total_issues"] == report["total_issues"]

    # директор видит отчёт у себя — со ссылкой на дашборд
    mine = (
        await async_client.get("/api/v1/notifications?type=DisciplineReport", headers=owner_headers)
    ).json()
    assert [item["title"] for item in mine["items"]] == [sent[0].title]
    assert mine["items"][0]["payload"]["deeplink"] == REPORT_DEEPLINK


@pytest.mark.asyncio
async def test_повтор_за_день_без_дублей_и_некому_слать_названо_прямо(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    people = await _people(sessionmaker, data_factory)
    # у руководителя ОТ канал приложения выключен — ему честно не уходит
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            NotificationChannelSettings(
                tenant_id=str(tenant.id), user_id=people["lead"], inapp_enabled=False
            )
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    first = (await async_client.post(RUN, headers=headers)).json()
    second = (await async_client.post(RUN, headers=headers)).json()

    assert first["notified"] == 2, "владелец и администратор; руководитель ОТ выключил канал"
    assert second["created"] is False
    assert second["notified"] == 0
    assert len(await _report_notifications(sessionmaker)) == 2


@pytest.mark.asyncio
async def test_стало_хуже_уходит_с_приоритетом_выше(sessionmaker, data_factory):
    people = await _people(sessionmaker, data_factory)
    today = date.today()

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        empty = await run_discipline_report(session, tid, today=today - timedelta(days=1))
        await session.commit()
    assert empty.notified == 2, "владелец и руководитель ОТ"

    await _seed(sessionmaker, data_factory)
    async with sessionmaker() as session:
        worse = await run_discipline_report(session, tid, today=today)
        await session.commit()
        again = await run_discipline_report(session, tid, today=today)
    assert worse.notified == 2
    assert again.notified == 0

    by_report: dict[str, set[NotificationPriority]] = {}
    for n in await _report_notifications(sessionmaker):
        by_report.setdefault(n.payload["entity_id"], set()).add(n.priority)
    assert by_report[str(empty.report.id)] == {NotificationPriority.MEDIUM}
    assert by_report[str(worse.report.id)] == {NotificationPriority.HIGH}
    assert {people["owner"], people["lead"]} == {
        n.user_id for n in await _report_notifications(sessionmaker)
    }
