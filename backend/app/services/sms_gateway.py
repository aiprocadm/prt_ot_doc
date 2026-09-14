"""Отправка SMS: шов к внешнему поставщику (SEC-68, разд. 68.1).

ЧТО БЫЛО. Одноразовый код внешнему получателю уходил ровно одним каналом —
почтой. Строка матрицы держала в остатке: «SMS как второй канал — внешний
поставщик, вне кода». Так и было: поставщика нет, и подключить его значило бы
писать новый код в момент подключения.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Поставщика выбирает владелец —
это правда не код. Но шов — код, и он делает подключение НАСТРОЙКОЙ. Здесь два
поставщика:

* ``disabled`` — умолчание. Честный отказ: канал не настроен. Не заглушка,
  рапортующая об успехе, — ровно та ошибка, за которую платформа уже платила
  (пустые адаптеры, уверявшие, что ведомство приняло данные).
* ``command`` — сообщение отдаётся внешней команде: CLI оператора связи,
  http-обёртка, скрипт развёртывания. Тот же приём, что у хранилища ключей
  (``core/key_provider.py``), и по той же причине: SDK конкретного оператора
  пришлось бы выкорчёвывать при смене поставщика, а команда есть у всех.

Команда получает номер первым аргументом, текст — в стандартный ввод. Код
возврата 0 — отправлено, иначе — отказ. Ответ поставщика в журнал не попадает:
в нём бывает сам текст сообщения, а в тексте — одноразовый код.

ПОЧЕМУ НЕ ЧЕРЕЗ ОБЩИЙ КОНТУР УВЕДОМЛЕНИЙ. Контур уведомлений адресуется по
``user_id``, а клиент портала — не пользователь системы: учётной записи у него
нет. Тот же довод, по которому письмо с кодом отдаётся почтовому провайдеру
напрямую (``services/portal_otp_delivery``).
"""

from __future__ import annotations

import asyncio
import enum
import logging
import re
import shlex
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DISABLED_PROVIDER = "disabled"
COMMAND_PROVIDER = "command"
KNOWN_PROVIDERS = (DISABLED_PROVIDER, COMMAND_PROVIDER)

DEFAULT_TIMEOUT_SECONDS = 15.0

#: Номер в международном виде: плюс и 8–15 цифр (E.164). Пробелы, скобки и
#: дефисы убираются до проверки — люди пишут номера как привыкли.
_E164_RE = re.compile(r"^\+\d{8,15}$")
_TRIM_RE = re.compile(r"[\s()\-]")


class SmsStatus(str, enum.Enum):
    SENT = "sent"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass(frozen=True)
class SmsOutcome:
    status: SmsStatus
    reason: str

    @property
    def delivered(self) -> bool:
        return self.status is SmsStatus.SENT


def normalize_phone(raw: str | None) -> str | None:
    """Привести номер к E.164 или вернуть ``None``, если это не номер.

    Российский номер, записанный с восьмёрки, приводится к ``+7``: иначе
    половина введённых людьми номеров отвергалась бы формально верно и
    совершенно бесполезно.
    """

    value = _TRIM_RE.sub("", (raw or "").strip())
    if not value:
        return None
    if value.startswith("8") and len(value) == 11:
        value = "+7" + value[1:]
    elif not value.startswith("+") and value.isdigit() and len(value) == 11:
        value = "+" + value
    return value if _E164_RE.match(value) else None


def provider_name(settings) -> str:
    raw = (getattr(settings, "sms_provider", "") or DISABLED_PROVIDER).strip().lower()
    return raw if raw in KNOWN_PROVIDERS else DISABLED_PROVIDER


def channel_ready(settings) -> bool:
    """Настроена ли отправка SMS вообще.

    Спрашивается ПРИ ВЫДАЧЕ ссылки, а не при входе: выдать привязку к телефону
    там, где сообщение уйти не может, значит запереть клиента снаружи.
    """

    if provider_name(settings) != COMMAND_PROVIDER:
        return False
    return bool((getattr(settings, "sms_command", "") or "").strip())


async def send_sms(*, phone: str, text: str, settings) -> SmsOutcome:
    """Отправить сообщение. Отказ честный: «не настроено» ≠ «отправлено»."""

    number = normalize_phone(phone)
    if number is None:
        return SmsOutcome(SmsStatus.FAILED, "Номер телефона выглядит неверным")

    if not channel_ready(settings):
        return SmsOutcome(
            SmsStatus.DISABLED,
            "Отправка SMS не настроена: обратитесь к администратору платформы",
        )

    command = shlex.split((getattr(settings, "sms_command", "") or "").strip())
    timeout = float(
        getattr(settings, "sms_command_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        or DEFAULT_TIMEOUT_SECONDS
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            number,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            process.communicate(text.encode("utf-8")), timeout=timeout
        )
    except FileNotFoundError:
        logger.error("sms_gateway.command_not_found")
        return SmsOutcome(SmsStatus.FAILED, "Отправка SMS настроена неверно")
    except TimeoutError:
        logger.error("sms_gateway.timeout")
        return SmsOutcome(SmsStatus.FAILED, "Оператор связи не ответил вовремя")
    except Exception:  # pragma: no cover - неожиданный сбой запуска
        logger.exception("sms_gateway.spawn_failed")
        return SmsOutcome(SmsStatus.FAILED, "Не удалось отправить SMS")

    if process.returncode != 0:
        # Пишем только поток ошибок: в стандартном выводе бывает сам текст, а в
        # тексте — одноразовый код.
        logger.error(
            "sms_gateway.rejected code=%s detail=%s",
            process.returncode,
            (stderr or b"").decode("utf-8", "replace")[:200],
        )
        return SmsOutcome(SmsStatus.FAILED, "Оператор связи не принял сообщение")

    return SmsOutcome(SmsStatus.SENT, "Код отправлен")


__all__ = [
    "COMMAND_PROVIDER",
    "DISABLED_PROVIDER",
    "KNOWN_PROVIDERS",
    "SmsOutcome",
    "SmsStatus",
    "channel_ready",
    "normalize_phone",
    "provider_name",
    "send_sms",
]
