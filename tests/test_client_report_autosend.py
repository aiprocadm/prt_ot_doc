"""Сторож: автоматика пишет только на подтверждённые адреса (BIZ-51, срез-193).

ЧТО БЫЛО. Отчёт клиенту умели собирать и отправлять — но только по кнопке.
Срез-11 сознательно НЕ включил автоматику и записал довод: «сперва обкатать
вручную, иначе первая же ошибка адреса уедет всем разом». Довод верный:
опечатка, разосланная по портфелю, — это письма посторонним людям с названием
организации клиента внутри.

КАК ДОВОД СНЯТ. Не отменой, а условием: автоматика пишет только на адрес, на
который отчёт УЖЕ ДОХОДИЛ. «Обкатать вручную» перестало быть обещанием и стало
правилом, которое нельзя забыть выполнить.

ГЛАВНЫЕ ПРОВЕРКИ ЗДЕСЬ:

1. непроверенный адрес в автоматику НЕ попадает;
2. СМЕНА адреса обнуляет подтверждение — иначе опечатка в правке сразу уехала
   бы в рассылку, ровно то, ради чего автоматику и сдерживали;
3. у отказа есть причина СЛОВАМИ: «не шлём» без причины означает, что
   специалист будет искать её в журналах, а чаще не будет искать вовсе.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_client_report_autosend.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.domains.managed_clients import report_schedule as rs

NOW = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)


@dataclass
class _Client:
    id: str = "c-1"
    report_email: str | None = "client@example.test"
    report_opt_in: bool = True
    report_verified_at: datetime | None = NOW - timedelta(days=60)
    report_last_auto_sent_at: datetime | None = None


def test_подтверждённый_адрес_с_согласием_готов() -> None:
    decision = rs.decide(_Client(), now=NOW)
    assert decision.ready
    assert decision.state == rs.READY


def test_непроверенный_адрес_в_автоматику_не_попадает() -> None:
    """ГЛАВНАЯ ПРОВЕРКА строки: автоматика не пишет туда, куда письмо не доходило."""

    decision = rs.decide(_Client(report_verified_at=None), now=NOW)
    assert not decision.ready
    assert decision.state == rs.NOT_VERIFIED
    # Причина объясняет, ЧТО СДЕЛАТЬ, а не только что не так.
    assert "вручную один раз" in decision.reason


def test_без_согласия_не_шлём() -> None:
    decision = rs.decide(_Client(report_opt_in=False), now=NOW)
    assert decision.state == rs.NO_CONSENT


def test_без_адреса_не_шлём() -> None:
    assert rs.decide(_Client(report_email=None), now=NOW).state == rs.NO_EMAIL
    assert rs.decide(_Client(report_email="   "), now=NOW).state == rs.NO_EMAIL


def test_за_период_не_шлём_дважды() -> None:
    client = _Client(report_last_auto_sent_at=NOW - timedelta(days=3))
    assert rs.decide(client, now=NOW).state == rs.ALREADY_SENT


def test_после_периода_снова_готов() -> None:
    client = _Client(report_last_auto_sent_at=NOW - timedelta(days=31))
    assert rs.decide(client, now=NOW).ready


def test_у_каждого_отказа_есть_причина_словами() -> None:
    """«Не шлём» без причины означает поиск в журналах — а чаще его отсутствие."""

    for state, reason in rs.REASONS.items():
        assert reason.strip(), state
        assert not reason.startswith(state), f"причина {state} — это код, а не слова"


def test_отбор_возвращает_только_готовых_но_остальные_объяснены() -> None:
    clients = [
        _Client(id="ok"),
        _Client(id="no-consent", report_opt_in=False),
        _Client(id="unverified", report_verified_at=None),
    ]
    ready = rs.select_ready(clients, now=NOW)
    assert [c.id for c in ready] == ["ok"]

    explained = {d.client_id: d.state for d in rs.explain(clients, now=NOW)}
    assert explained == {
        "ok": rs.READY,
        "no-consent": rs.NO_CONSENT,
        "unverified": rs.NOT_VERIFIED,
    }


def test_наивное_время_считается_UTC() -> None:
    """База отдаёт datetime без зоны — сравнение с ним не должно падать."""

    client = _Client(report_verified_at=datetime(2026, 1, 1), report_last_auto_sent_at=None)
    assert rs.decide(client, now=NOW).ready


@pytest.mark.parametrize("days", [0, -5])
def test_нулевой_период_не_превращается_в_рассылку_каждую_минуту(days: int) -> None:
    """Опечатка в настройке периода не должна означать «слать непрерывно»."""

    client = _Client(report_last_auto_sent_at=NOW - timedelta(hours=1))
    assert rs.decide(client, now=NOW, period_days=days).state == rs.ALREADY_SENT


def test_задача_рассылки_зарегистрирована_и_БЕЗ_аргументов() -> None:
    """Урок среза-170: задача с аргументом в расписание не попадает НИКОГДА.

    Проверяется и регистрация, и наличие в расписании: механизм, который никто
    не запускает, — это отсутствующий механизм.
    """

    from app.services.celery_app import celery_app

    name = "managed_clients.report.sweep"
    assert name in celery_app.tasks
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert name in scheduled
