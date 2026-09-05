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

Срез-60 — письмо «клиенту при аренде»: тем же получателям вторым
уведомлением канала «почта» со своим согласием (``email_enabled``), своим
ключом дедупликации и честным итогом доставщика — без SMTP письмо помечено
«пропущено», а не «отправлено», и карточка в приложении от этого не двоится.
"""

from __future__ import annotations

import smtplib
from datetime import date, timedelta
from email.message import EmailMessage
from types import SimpleNamespace

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
    NotificationStatus,
    NotificationType,
)
from app.modules.notifications.delivery import deliver_notification
from app.services.discipline_report import run_discipline_report
from app.services.discipline_report_delivery import (
    REPORT_DEEPLINK,
    build_report_letter,
    report_dedup_key,
    report_letter_dedup_key,
)
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


async def _report_notifications(
    sessionmaker, channel: NotificationChannel | None = None
) -> list[Notification]:
    stmt = select(Notification).where(
        Notification.type == NotificationType.DISCIPLINE_REPORT,
        Notification.deleted_at.is_(None),
    )
    if channel is not None:
        stmt = stmt.where(Notification.channel == channel)
    async with sessionmaker() as session:
        return list((await session.execute(stmt)).scalars().all())


def _smtp_settings(*, configured: bool) -> SimpleNamespace:
    """Настройки доставщика: почта настроена администратором или нет."""

    return SimpleNamespace(
        notifications_delivery_enabled=configured,
        notifications_max_delivery_attempts=3,
        smtp_host="smtp.local" if configured else "",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_from="no-reply@platform.example",
        smtp_use_tls=True,
        admin_email="admin@platform.example",
    )


class _FakeSMTP:
    """Заглушка SMTP: запоминает письмо вместо отправки по сети."""

    sent: list[EmailMessage] = []

    def __init__(self, host, port, timeout=10):  # noqa: ARG002
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):  # noqa: ARG002
        pass

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


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
    # владелец, руководитель ОТ и сам администратор — трое; письмо — им же
    assert body["notified"] == 3
    assert body["mailed"] == 3
    assert body["summary"] == (
        "Отчёт собран, уведомление ушло 3 получателям, " "письмо поставлено в очередь 3 получателям"
    )

    sent = await _report_notifications(sessionmaker, NotificationChannel.INAPP)
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

    # письмо — тем же троим, второй записью канала «почта» со своим ключом
    letters = await _report_notifications(sessionmaker, NotificationChannel.EMAIL)
    assert {n.user_id for n in letters} == recipients
    subject, text = build_report_letter(await _report_row(sessionmaker, report["id"]))
    for n in letters:
        assert n.status == NotificationStatus.QUEUED, "отправит доставщик, не запуск"
        assert n.dedup_key == report_letter_dedup_key(report["id"], n.user_id)
        assert n.title == subject == sent[0].title
        assert n.body == text
        assert n.payload["entity_id"] == report["id"]
    # текст письма: период целиком, та же сводка, где искать подробности
    assert "Отчёт о состоянии по дисциплинам за период" in text
    assert report["summary"] in text
    assert REPORT_DEEPLINK in text
    assert "сформировано автоматически" in text

    # директор видит отчёт у себя — карточку со ссылкой на дашборд, и письмо
    # рядом в журнале (канал виден в списке, фильтр по каналу есть)
    mine = (
        await async_client.get(
            "/api/v1/notifications?type=DisciplineReport&channel=inapp", headers=owner_headers
        )
    ).json()
    assert [item["title"] for item in mine["items"]] == [sent[0].title]
    assert mine["items"][0]["payload"]["deeplink"] == REPORT_DEEPLINK
    mail = (
        await async_client.get(
            "/api/v1/notifications?type=DisciplineReport&channel=email", headers=owner_headers
        )
    ).json()
    assert [item["title"] for item in mail["items"]] == [subject]


async def _report_row(sessionmaker, report_id: str):
    from app.models.discipline_reports import DisciplineStatusReport

    async with sessionmaker() as session:
        return await session.get(DisciplineStatusReport, report_id)


@pytest.mark.asyncio
async def test_повтор_за_день_без_дублей_и_некому_слать_названо_прямо(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    people = await _people(sessionmaker, data_factory)
    # у руководителя ОТ выключен канал приложения, у владельца — почта:
    # каждому честно не уходит своё, а другой канал у него живёт
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add_all(
            [
                NotificationChannelSettings(
                    tenant_id=str(tenant.id), user_id=people["lead"], inapp_enabled=False
                ),
                NotificationChannelSettings(
                    tenant_id=str(tenant.id), user_id=people["owner"], email_enabled=False
                ),
            ]
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    first = (await async_client.post(RUN, headers=headers)).json()
    second = (await async_client.post(RUN, headers=headers)).json()

    assert first["notified"] == 2, "владелец и администратор; руководитель ОТ выключил канал"
    assert first["mailed"] == 2, "руководитель ОТ и администратор; владелец выключил почту"
    assert second["created"] is False
    assert second["notified"] == 0
    assert second["mailed"] == 0
    cards = await _report_notifications(sessionmaker, NotificationChannel.INAPP)
    letters = await _report_notifications(sessionmaker, NotificationChannel.EMAIL)
    assert {n.user_id for n in cards} == {people["owner"], admin_id(cards, people)}
    assert {n.user_id for n in letters} == {people["lead"], admin_id(cards, people)}


def admin_id(rows: list[Notification], people: dict[str, str]) -> str:
    """Администратор из ``make_auth_headers`` — единственный получатель не из ``_people``."""

    return next(n.user_id for n in rows if n.user_id not in people.values())


@pytest.mark.asyncio
async def test_некому_слать_названо_прямо_и_по_каналам(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    """Итог «собрать сейчас» говорит по каждому каналу своё: у единственного
    получателя выключена почта — письмо «никому не ушло», а не «собран»."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        admin = await data_factory.create_user(
            tenant=tenant, role=RoleEnum.ADMIN, email="admin-dr@example.com", session=session
        )
        session.add(
            NotificationChannelSettings(
                tenant_id=str(tenant.id), user_id=str(admin.id), email_enabled=False
            )
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, email="admin-dr@example.com")

    body = (await async_client.post(RUN, headers=headers)).json()

    assert body["notified"] == 1
    assert body["mailed"] == 0
    assert body["summary"] == (
        "Отчёт собран, уведомление ушло 1 получателю, "
        "письмо никому не ушло: почта у получателей выключена"
    )


@pytest.mark.asyncio
async def test_письмо_отправляет_доставщик_и_без_smtp_честно_пропускает(
    sessionmaker, data_factory, monkeypatch
):
    """Доставка по образцу ``client_report_mail``: настроена почта — письмо
    ушло на адрес получателя с темой отчёта; не настроена — запись помечена
    «пропущено» с причиной, и карточка в приложении не двоится."""

    people = await _people(sessionmaker, data_factory)
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        outcome = await run_discipline_report(session, str(tenant.id), today=date.today())
        await session.commit()
    assert outcome.mailed == 2

    async with sessionmaker() as session:
        letters = {
            n.user_id: n
            for n in (
                await session.execute(
                    select(Notification).where(
                        Notification.type == NotificationType.DISCIPLINE_REPORT,
                        Notification.channel == NotificationChannel.EMAIL,
                    )
                )
            )
            .scalars()
            .all()
        }
        owner_letter, lead_letter = letters[people["owner"]], letters[people["lead"]]

        # почта настроена: письмо собрано и ушло на адрес владельца
        result = await deliver_notification(
            session, owner_letter, settings=_smtp_settings(configured=True)
        )
        assert result.delivered
        assert owner_letter.status == NotificationStatus.SENT
        assert owner_letter.payload["delivery"]["outcome"] == "delivered"
        msg = _FakeSMTP.sent[-1]
        assert msg["To"] == "owner-dr@example.com"
        assert msg["Subject"] == owner_letter.title
        assert outcome.report.summary in msg.get_content()

        # почта не настроена: не «отправлено», а «пропущено» с причиной
        result = await deliver_notification(
            session, lead_letter, settings=_smtp_settings(configured=False)
        )
        assert result.skipped
        assert lead_letter.status == NotificationStatus.SENT
        assert lead_letter.payload["delivery"]["outcome"] == "skipped"
        assert "SMTP" in (lead_letter.last_error or "")
        await session.commit()

    # пропуск письма не породил второй карточки в приложении
    cards = await _report_notifications(sessionmaker, NotificationChannel.INAPP)
    assert [n.dedup_key for n in cards if n.user_id == people["lead"]] == [
        report_dedup_key(str(outcome.report.id), people["lead"])
    ]
    assert len(_FakeSMTP.sent) == 1


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
    assert empty.mailed == 2, "письмо — им же"

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
    # приоритет один на оба канала: письмо о том же отчёте не «важнее» карточки
    assert by_report[str(empty.report.id)] == {NotificationPriority.MEDIUM}
    assert by_report[str(worse.report.id)] == {NotificationPriority.HIGH}
    assert {people["owner"], people["lead"]} == {
        n.user_id for n in await _report_notifications(sessionmaker)
    }
