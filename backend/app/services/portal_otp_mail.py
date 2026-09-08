"""Доставка одноразового кода внешнему получателю (SEC-68, разд. 68.1).

Модель угроз внешнего периметра держала одну строку красной: **пересланная
третьему лицу ссылка**. Одноразовость помогает лишь отчасти — кто первым
откроет, тот и войдёт, и владелец ссылки об этом не узнает. Привязка к
получателю закрывает именно это: ссылка остаётся входным билетом, но обменять
её на сеанс можно только кодом, пришедшим НА УКАЗАННЫЙ АДРЕС.

## Решения

**1. Канал уже есть — почта.** Заводить SMS ради одного сценария значило бы
завести второго внешнего поставщика и второй набор ключей. Письмо продукт
отправлять умеет, бренд арендатора подставляется сам (BIZ-52 срез-10).

**2. Клиент портала — НЕ пользователь системы.** У него нет учётной записи,
поэтому обычный контур уведомлений (он адресуется по ``user_id``) не годится:
письмо отдаётся почтовому провайдеру напрямую — тот же приём, что у отчёта
клиенту (``services/client_report_mail``).

**3. Сборка письма отделена от отправки.** Текст проверяется без SMTP, а
отправка — отдельным шагом: иначе проверить, что в письме нет ссылки и нет
названия арендатора, можно было бы только на живом сервере.

**4. В письме нет ни ссылки, ни кода в теме.** Ссылка у получателя уже есть;
повторять её значит удваивать то, что и так утекает при пересылке. Тема без
кода — темы писем видны на экране блокировки телефона.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from types import SimpleNamespace

from app.core.config import get_settings
from app.modules.notifications.providers import EmailProvider, NotificationContact

__all__ = [
    "OtpSendOutcome",
    "OtpSendStatus",
    "build_otp_letter",
    "mail_channel_ready",
    "send_otp_code",
]


class OtpSendStatus(str, enum.Enum):
    SENT = "sent"
    MAIL_DISABLED = "mail_disabled"
    FAILED = "failed"


@dataclass(frozen=True)
class OtpSendOutcome:
    status: OtpSendStatus
    reason: str

    @property
    def delivered(self) -> bool:
        return self.status is OtpSendStatus.SENT


def mail_channel_ready() -> bool:
    """Настроена ли доставка вообще.

    Проверяется ПРИ ВЫДАЧЕ ссылки, а не при входе: выдать ссылку с привязкой
    там, где письмо уйти не может, значит запереть клиента снаружи — и узнает
    он об этом позже специалиста.
    """

    settings = get_settings()
    return bool(
        getattr(settings, "notifications_delivery_enabled", False)
        and (settings.smtp_host or "").strip()
    )


def build_otp_letter(code: str, *, ttl_minutes: int) -> tuple[str, str]:
    """Тема и текст письма. Отдельно от отправки — чтобы проверять без SMTP."""

    subject = "Код для входа в личный кабинет"
    body = "\n".join(
        [
            "Код для входа по вашей ссылке:",
            "",
            code,
            "",
            f"Код действует {ttl_minutes} мин. и вводится один раз.",
            "",
            "Если вы не запрашивали вход, ничего делать не нужно: без кода "
            "по ссылке войти нельзя.",
        ]
    )
    return subject, body


async def send_otp_code(
    *, tenant_id: str, recipient: str, code: str, ttl_minutes: int
) -> OtpSendOutcome:
    """Отправить код на указанный при выдаче ссылки адрес."""

    if not mail_channel_ready():
        return OtpSendOutcome(
            OtpSendStatus.MAIL_DISABLED,
            "Доставка кода не настроена: обратитесь к администратору платформы",
        )

    subject, body = build_otp_letter(code, ttl_minutes=ttl_minutes)
    provider = EmailProvider(get_settings())
    # Провайдер читает у сообщения только заголовок, тело и арендатора —
    # строку в журнале уведомлений здесь заводить не за кого.
    letter = SimpleNamespace(title=subject, body=body, tenant_id=str(tenant_id))
    result = await provider.deliver(
        notification=letter, contact=NotificationContact(email=recipient)
    )
    if result.delivered:
        return OtpSendOutcome(OtpSendStatus.SENT, "Код отправлен")
    return OtpSendOutcome(OtpSendStatus.FAILED, "Почтовый сервер не принял письмо с кодом")
