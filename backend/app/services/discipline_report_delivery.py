"""Доставка отчёта о состоянии по дисциплинам (Доп. №1 разд. 57.4, срез-51).

ТЗ называет отчёт «авто-отчётом для клиента при аренде». Отчёт среза-50
лежит в базе и ждёт, пока директор сам зайдёт на дашборд, — это архив, а не
доставка. Здесь новый отчёт уходит штатным уведомлением в приложении тем,
кто отвечает за всю безопасность предприятия.

## Решения

**1. Получатели — по роли, а не «все, кто читает аналитику».** Аналитику
читают семь ролей, включая HR и линейных руководителей; еженедельный отчёт
обо всём предприятии для них — шум. Уходит владельцу, администратору и
руководителю службы ОТ: это те, с кого спросят за все дисциплины сразу.
Отдельного справочника «кому слать отчёт» не заводится — им стало бы
нечего заполнять, пока таких отчётов один.

**2. Одно уведомление на отчёт и получателя.** Ключ дедупликации —
``discipline_report:<report_id>:<user_id>``: тик ретраится, «собрать сейчас»
нажимают после тика — отчёт за дату один, и уведомление о нём одно.

**3. «Стало хуже» — выше приоритет.** Итог отчёта уже сравнён с прошлым;
рост нарушений уходит с ``HIGH``, остальное — ``MEDIUM``. Сам текст
уведомления — сводка отчёта: она уже отвечает «что, что изменилось, что
делать», второй пересказ разошёлся бы с ней.

**4. Канал — только приложение.** Письмо требует согласия и настроек
доставки (у аутсорсинга — ``client_report_mail``); это отдельный шаг.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discipline_reports import DisciplineStatusReport
from app.models.identity import User
from app.models.notifications import (
    NotificationChannel,
    NotificationPriority,
    NotificationType,
)
from app.models.tenant_billing import RoleEnum
from app.services.notifications import send_notification

__all__ = [
    "REPORT_DEEPLINK",
    "REPORT_RECIPIENT_ROLES",
    "deliver_discipline_report",
    "report_dedup_key",
]

#: Кому уходит отчёт обо всём предприятии (см. решение 1 в докстринге модуля).
REPORT_RECIPIENT_ROLES: tuple[RoleEnum, ...] = (
    RoleEnum.OWNER,
    RoleEnum.ADMIN,
    RoleEnum.OT_PB_LEAD,
)

#: Карточка отчёта живёт на управленческом дашборде.
REPORT_DEEPLINK = "/dashboard"


def report_dedup_key(report_id: str, user_id: str) -> str:
    return f"discipline_report:{report_id}:{user_id}"


def _priority(report: DisciplineStatusReport) -> NotificationPriority:
    delta = ((report.payload or {}).get("totals") or {}).get("delta")
    if isinstance(delta, int) and delta > 0:
        return NotificationPriority.HIGH
    return NotificationPriority.MEDIUM


async def deliver_discipline_report(session: AsyncSession, report: DisciplineStatusReport) -> int:
    """Отправить отчёт получателям. Возвращает число созданных уведомлений.

    Ничего не коммитит — транзакцией владеет вызывающий. Получатель, который
    выключил канал приложения, честно не считается: уведомления у него нет.
    """

    users = (
        (
            await session.execute(
                select(User).where(
                    User.tenant_id == report.tenant_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    User.role.in_(REPORT_RECIPIENT_ROLES),
                )
            )
        )
        .scalars()
        .all()
    )
    title = f"Отчёт о состоянии по дисциплинам за {report.period_end.strftime('%d.%m.%Y')}"
    priority = _priority(report)
    sent = 0
    for user in users:
        created = await send_notification(
            session,
            tenant_id=report.tenant_id,
            user_id=str(user.id),
            channel=NotificationChannel.INAPP,
            type=NotificationType.DISCIPLINE_REPORT,
            title=title,
            body=report.summary,
            payload={
                "entity_type": "discipline_status_report",
                "entity_id": str(report.id),
                "deeplink": REPORT_DEEPLINK,
                "period_end": report.period_end.isoformat(),
                "total_issues": int(report.total_issues),
            },
            dedup_key=report_dedup_key(str(report.id), str(user.id)),
            priority=priority,
        )
        sent += int(created is not None)
    return sent
