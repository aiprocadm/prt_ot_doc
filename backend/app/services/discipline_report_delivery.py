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

**4. Письмо — вторым уведомлением, канал «почта» (срез-60).** ТЗ зовёт
отчёт «авто-отчётом для клиента при аренде»: клиент аренды — директор, а его
рабочее место не всегда открыто, письмо же доходит и в закрытое. Три условия
те же, что у письма клиенту аутсорсинга (``client_report_mail``): согласие,
настройка, доставка. Согласие — настройка почты у самого получателя
(``email_enabled``: выключил — письма нет, карточка в приложении остаётся;
выключил приложение — письмо всё равно уходит: два канала, два согласия).
Настройка — SMTP у администратора платформы. Доставка — штатный контур
уведомлений: письмо не отдаётся почтовому серверу «мимо журнала», как у
аутсорсинга (там клиент не пользователь), а лежит в журнале уведомлений
рядом с карточкой и получает честный итог доставщика: без SMTP —
«пропущено» с причиной, а не «отправлено». Ключ дедупликации — тот же с
суффиксом ``:email``: повтор тика не шлёт второе письмо.

**5. Текст письма — не копия карточки.** У карточки есть ссылка «открыть
дашборд», у письма её нет; поэтому письмо называет период целиком, несёт ту
же сводку и говорит словами, где искать подробности.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    "ReportDelivery",
    "build_report_letter",
    "deliver_discipline_report",
    "report_dedup_key",
    "report_letter_dedup_key",
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


def report_letter_dedup_key(report_id: str, user_id: str) -> str:
    return f"{report_dedup_key(report_id, user_id)}:email"


@dataclass(frozen=True)
class ReportDelivery:
    """Сколько уведомлений создано по каналам: карточек в приложении и писем.

    Письмо здесь — поставлено в очередь, а не доставлено: отправляет
    доставщик уведомлений, и итог (ушло / пропущено без SMTP) он пишет на
    самой записи.
    """

    in_app: int = 0
    email: int = 0


def _report_title(report: DisciplineStatusReport) -> str:
    return f"Отчёт о состоянии по дисциплинам за {report.period_end.strftime('%d.%m.%Y')}"


def build_report_letter(report: DisciplineStatusReport) -> tuple[str, str]:
    """Тема и текст письма. Отдельно от отправки — чтобы проверять без SMTP."""

    period = (
        f"{report.period_start.strftime('%d.%m.%Y')} — {report.period_end.strftime('%d.%m.%Y')}"
    )
    lines = [
        f"Отчёт о состоянии по дисциплинам за период {period}.",
        "",
        report.summary,
        "",
        "Подробности по каждой дисциплине — на управленческом дашборде "
        f"в приложении ({REPORT_DEEPLINK}).",
        "",
        "Письмо сформировано автоматически по данным вашей организации. "
        "Отключить его можно в настройках уведомлений (канал «почта»).",
    ]
    return _report_title(report), "\n".join(lines)


def _priority(report: DisciplineStatusReport) -> NotificationPriority:
    delta = ((report.payload or {}).get("totals") or {}).get("delta")
    if isinstance(delta, int) and delta > 0:
        return NotificationPriority.HIGH
    return NotificationPriority.MEDIUM


async def deliver_discipline_report(
    session: AsyncSession, report: DisciplineStatusReport
) -> ReportDelivery:
    """Отправить отчёт получателям: карточку в приложении и письмо каждому.

    Ничего не коммитит — транзакцией владеет вызывающий. Получатель, который
    выключил канал, честно не считается: уведомления в этом канале у него
    нет; каналы независимы (см. решение 4 в докстринге модуля).
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
    title = _report_title(report)
    subject, letter = build_report_letter(report)
    priority = _priority(report)
    payload = {
        "entity_type": "discipline_status_report",
        "entity_id": str(report.id),
        "deeplink": REPORT_DEEPLINK,
        "period_end": report.period_end.isoformat(),
        "total_issues": int(report.total_issues),
    }
    in_app = 0
    email = 0
    for user in users:
        card = await send_notification(
            session,
            tenant_id=report.tenant_id,
            user_id=str(user.id),
            channel=NotificationChannel.INAPP,
            type=NotificationType.DISCIPLINE_REPORT,
            title=title,
            body=report.summary,
            payload=payload,
            dedup_key=report_dedup_key(str(report.id), str(user.id)),
            priority=priority,
        )
        in_app += int(card is not None)
        # Адрес у пользователя есть всегда (это его логин); доставщик возьмёт
        # его сам или адрес из настроек уведомлений, если тот указан.
        mail = await send_notification(
            session,
            tenant_id=report.tenant_id,
            user_id=str(user.id),
            channel=NotificationChannel.EMAIL,
            type=NotificationType.DISCIPLINE_REPORT,
            title=subject,
            body=letter,
            payload=payload,
            dedup_key=report_letter_dedup_key(str(report.id), str(user.id)),
            priority=priority,
        )
        email += int(mail is not None)
    return ReportDelivery(in_app=in_app, email=email)
