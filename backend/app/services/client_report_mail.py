"""BIZ-51 срез-11 (Доп. №1 разд. 51.3): отправка отчёта аудита клиенту.

Последний пункт разд. 51.3 — «авто-генерируемый периодический отчёт о
состоянии соответствия». Отчёты копятся с среза-7, но уходить им было некуда:
у карточки клиента не было ни адреса, ни согласия на рассылку.

## Решения

**Адрес и согласие — два разных условия.** Знать e-mail и иметь право на него
писать — не одно и то же. Рассылка без основания бьёт и по закону, и по
репутации аутсорсера, поэтому отправка без согласия отказывается СЛОВАМИ, а не
происходит молча.

**Итог отправки честный, по причинам.** «Не отправлено» без объяснения
одинаково выглядит и когда клиент не давал согласия, и когда на сервере не
настроен SMTP. Первое чинит специалист, второе — администратор, и путать их
нельзя.

**Клиент — НЕ пользователь системы.** У Shared-клиента нет учётной записи,
поэтому обычный контур уведомлений (он адресуется по ``user_id``) здесь не
годится: письмо собирается и отдаётся почтовому провайдеру напрямую. Бренд
партнёра при этом сохраняется — провайдер сам подставляет имя отправителя и
адрес для ответа (BIZ-52 срез-10).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from types import SimpleNamespace

from app.core.config import get_settings
from app.models.client_changes import ClientAuditReport
from app.models.managed_clients import ManagedClient
from app.modules.notifications.providers import EmailProvider, NotificationContact

__all__ = [
    "REASONS",
    "ReportSendOutcome",
    "ReportSendStatus",
    "build_letter",
    "send_report_to_client",
]


class ReportSendStatus(str, enum.Enum):
    SENT = "sent"
    NO_EMAIL = "no_email"
    NO_CONSENT = "no_consent"
    MAIL_DISABLED = "mail_disabled"
    FAILED = "failed"


#: Человеческие причины: их читает специалист, а не разработчик.
REASONS: dict[ReportSendStatus, str] = {
    ReportSendStatus.SENT: "Отчёт отправлен",
    ReportSendStatus.NO_EMAIL: "У клиента не указан адрес для отчётов",
    ReportSendStatus.NO_CONSENT: (
        "Клиент не давал согласия на получение отчётов — включите его в карточке"
    ),
    ReportSendStatus.MAIL_DISABLED: "Отправка почты не настроена на сервере",
    ReportSendStatus.FAILED: "Почтовый сервер отклонил письмо",
}


@dataclass(frozen=True)
class ReportSendOutcome:
    status: ReportSendStatus
    reason: str
    recipient: str | None = None


def build_letter(client: ManagedClient, report: ClientAuditReport) -> tuple[str, str]:
    """Тема и текст письма. Отдельно от отправки — чтобы проверять без SMTP."""

    period = (
        f"{report.period_start.strftime('%d.%m.%Y')}" f" — {report.period_end.strftime('%d.%m.%Y')}"
    )
    subject = f"Отчёт о состоянии охраны труда: {client.name} ({period})"
    actions = list((report.payload or {}).get("actions") or [])
    lines = [f"Отчёт за период {period}.", "", report.summary]
    if actions:
        lines += ["", "Что нужно сделать:"]
        lines += [f"— {item}" for item in actions]
    lines += ["", "Письмо сформировано автоматически по данным вашей организации."]
    return subject, "\n".join(lines)


async def send_report_to_client(
    client: ManagedClient, report: ClientAuditReport
) -> ReportSendOutcome:
    """Отправить отчёт на адрес клиента, если он его разрешил."""

    recipient = (client.report_email or "").strip()
    if not recipient:
        return ReportSendOutcome(ReportSendStatus.NO_EMAIL, REASONS[ReportSendStatus.NO_EMAIL])
    if not client.report_opt_in:
        return ReportSendOutcome(ReportSendStatus.NO_CONSENT, REASONS[ReportSendStatus.NO_CONSENT])

    subject, body = build_letter(client, report)
    provider = EmailProvider(get_settings())
    # Провайдер читает у сообщения только заголовок, текст и арендатора —
    # строку в журнале уведомлений здесь заводить не за кого: клиент не
    # пользователь системы.
    letter = SimpleNamespace(title=subject, body=body, tenant_id=str(client.tenant_id))
    result = await provider.deliver(
        notification=letter, contact=NotificationContact(email=recipient)
    )

    if result.delivered:
        return ReportSendOutcome(ReportSendStatus.SENT, REASONS[ReportSendStatus.SENT], recipient)
    detail = (result.detail or "").strip()
    if result.skipped:
        # Провайдер пропускает отправку, когда почта не настроена вовсе —
        # это забота администратора, а не специалиста по охране труда.
        return ReportSendOutcome(
            ReportSendStatus.MAIL_DISABLED,
            REASONS[ReportSendStatus.MAIL_DISABLED],
            recipient,
        )
    return ReportSendOutcome(
        ReportSendStatus.FAILED,
        f"{REASONS[ReportSendStatus.FAILED]}: {detail}"
        if detail
        else REASONS[ReportSendStatus.FAILED],
        recipient,
    )
