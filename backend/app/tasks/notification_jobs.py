"""Задачи доставки уведомлений (ARCH-4 decomposition; RC-011 delivery).

Отправка одного сообщения и почасовой разбор очереди
(``notifications.dispatch_pending``) отдают работу
:mod:`app.modules.notifications.delivery` — провайдеры по каналам, честный
статус и повышение канала при отказе.

**Срез-113: сканер правил напоминаний удалён.** Здесь жила задача
``reminders.scan``: ежечасно обходила арендаторов, читала ``ReminderRule`` и
рассылала напоминания по срокам обучения, СИЗ и проверок. Правило нельзя было
создать НИ ОДНИМ способом — ни ручкой API, ни сидом, ни миграцией с данными, —
поэтому обход всегда находил ноль правил и каждый час тратил такты впустую.
Хуже: код выглядел работающим механизмом напоминаний, хотя напоминания в
продукте давно делает другое — библиотека правил дисциплин
(``domains/rules_library``), события сроков (``services/discipline_deadline_events``),
полосы SLA общего календаря и ежедневная ``tasks.reminders.dispatch``. Держать
второй, недостижимый механизм значило хранить два места правды, одно из которых
никогда не выполняется.

Модель ``ReminderRule``, её таблица, RLS и миграции НЕ удалялись: данные
арендаторов трогать нельзя, а вернуть механизм (уже с ручками) при
необходимости проще на существующей схеме.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.tenant import tenant_context
from app.db import AsyncSessionLocal, ensure_tenant_schema, session_scope
from app.models.models import (
    Tenant,
)
from app.models.notifications import (
    Notification,
    NotificationStatus,
)
from app.modules.notifications.delivery import (
    deliver_notification,
    scan_pending_notifications,
)
from app.services.celery_app import celery_app
from app.tasks._shared import _run_coroutine

settings = get_settings()


@celery_app.task(name="notifications.dispatch")
def dispatch_notification_job(notification_id: str, tenant_slug: str = "test") -> int:
    return _run_coroutine(
        _dispatch_notification_job(notification_id=notification_id, tenant_slug=tenant_slug)
    )


async def _dispatch_notification_job(*, notification_id: str, tenant_slug: str = "test") -> int:
    async with session_scope(tenant=tenant_slug) as session:
        notification = (
            await session.execute(select(Notification).where(Notification.id == notification_id))
        ).scalar_one_or_none()
        if notification is None or notification.status != NotificationStatus.QUEUED:
            return 0
        # RC-011: real provider delivery + honest status + channel-tier escalation
        # (replaces the former stub that set status=SENT without calling any provider).
        await deliver_notification(session, notification)
    return 1


@celery_app.task(name="notifications.dispatch_pending")
def dispatch_pending_notifications_job() -> int:
    """Beat job: deliver all due QUEUED notifications for every active tenant (RC-011)."""
    return _run_coroutine(_dispatch_pending_notifications_job())


async def _dispatch_pending_notifications_job() -> int:
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as tenant_session:
                processed += await scan_pending_notifications(tenant_session)
    return processed
