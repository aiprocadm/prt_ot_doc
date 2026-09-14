"""Кому автоматика вправе слать отчёт (BIZ-51, разд. 51.3).

ЧТО БЫЛО. Срез-11 завёл адрес и согласие и сознательно НЕ включил
автоматическую рассылку, записав довод: «сперва обкатать вручную, иначе первая
же ошибка адреса уедет всем разом». Довод верный — опечатка в адресе,
разосланная по всему портфелю, это письма посторонним людям с названием
организации клиента внутри.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Довод снимается не отменой, а
УСЛОВИЕМ: автоматика пишет только на адреса, на которые отчёт УЖЕ ДОХОДИЛ.
Адрес, подтверждённый хотя бы одной успешной доставкой, ошибочным быть не
может. «Обкатать вручную» перестаёт быть обещанием и становится правилом,
которое нельзя забыть выполнить.

ЧЕТЫРЕ УСЛОВИЯ, И КАЖДОЕ ОТВЕЧАЕТ НА СВОЙ ВОПРОС:

* адрес есть            — куда слать;
* согласие есть         — вправе ли мы писать;
* адрес подтверждён     — не уедет ли письмо постороннему;
* период не отработан   — не пришлём ли второй раз за тот же период.

Причина отказа называется словами по каждому: «не шлём» без причины означает,
что специалист будет искать её в журналах, а чаще не будет искать вовсе.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

READY = "ready"
NO_EMAIL = "no_email"
NO_CONSENT = "no_consent"
NOT_VERIFIED = "not_verified"
ALREADY_SENT = "already_sent"

REASONS = {
    READY: "Готов к автоматической отправке",
    NO_EMAIL: "Не указан адрес для отчёта",
    NO_CONSENT: "Клиент не дал согласия на рассылку",
    NOT_VERIFIED: (
        "Адрес ещё не подтверждён доставкой: отправьте отчёт вручную один раз — "
        "автоматика пишет только туда, куда письмо уже доходило"
    ),
    ALREADY_SENT: "За этот период отчёт уже отправлен",
}

#: Раз в сколько дней уходит автоматический отчёт. Месяц — период, за который
#: у клиента накапливается что-то, о чём стоит писать; чаще — это шум, и его
#: перестают открывать.
DEFAULT_PERIOD_DAYS = 30


@dataclass(frozen=True)
class AutoSendDecision:
    client_id: str
    state: str
    reason: str

    @property
    def ready(self) -> bool:
        return self.state == READY


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def decide(client, *, now: datetime | None = None, period_days: int = DEFAULT_PERIOD_DAYS):
    """Решение по одному клиенту. Порядок проверок — от дешёвого к дорогому."""

    moment = now or datetime.now(tz=timezone.utc)
    client_id = str(getattr(client, "id", ""))

    if not (getattr(client, "report_email", "") or "").strip():
        return AutoSendDecision(client_id, NO_EMAIL, REASONS[NO_EMAIL])
    if not getattr(client, "report_opt_in", False):
        return AutoSendDecision(client_id, NO_CONSENT, REASONS[NO_CONSENT])
    if _as_utc(getattr(client, "report_verified_at", None)) is None:
        return AutoSendDecision(client_id, NOT_VERIFIED, REASONS[NOT_VERIFIED])

    last = _as_utc(getattr(client, "report_last_auto_sent_at", None))
    if last is not None and moment - last < timedelta(days=max(1, period_days)):
        return AutoSendDecision(client_id, ALREADY_SENT, REASONS[ALREADY_SENT])

    return AutoSendDecision(client_id, READY, REASONS[READY])


def select_ready(clients, *, now: datetime | None = None, period_days: int = DEFAULT_PERIOD_DAYS):
    """Кому слать сейчас. Остальные не теряются — см. :func:`explain`."""

    return [
        client
        for client in clients
        if decide(client, now=now, period_days=period_days).ready
    ]


def explain(clients, *, now: datetime | None = None, period_days: int = DEFAULT_PERIOD_DAYS):
    """Почему остальным не шлём. Нужен экрану и разбору обращений.

    Без этого «почему клиенту не приходит отчёт» выяснялось бы чтением кода.
    """

    return [decide(client, now=now, period_days=period_days) for client in clients]


__all__ = [
    "ALREADY_SENT",
    "DEFAULT_PERIOD_DAYS",
    "NOT_VERIFIED",
    "NO_CONSENT",
    "NO_EMAIL",
    "READY",
    "REASONS",
    "AutoSendDecision",
    "decide",
    "explain",
    "select_ready",
]
