"""BIZ-51 срез-11: отправка отчёта клиенту (Доп. №1 разд. 51.3).

Правила проверяются без SMTP: письмо собирается отдельной функцией, а решение
«слать или отказать» принимается до всякой сети. Закрепляется главное:

* адрес и согласие — ДВА условия, и адреса без согласия недостаточно;
* каждый отказ несёт человеческую причину, а не молчит;
* письмо содержит период, итог и список действий — то, ради чего отчёт нужен.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.client_report_mail import (
    ReportSendStatus,
    build_letter,
    send_report_to_client,
)


def _client(**extra):
    base = dict(
        id="mc1",
        tenant_id="tenant-1",
        name="ООО Ромашка",
        report_email="client@example.com",
        report_opt_in=True,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _report(**extra):
    base = dict(
        id="r1",
        period_start=date(2026, 8, 11),
        period_end=date(2026, 8, 18),
        overall="red",
        summary="Изменений за период: 2. Просрочено и не оформлено — Медосмотры: не оформлено вовсе: 2.",
        payload={"actions": ["Медосмотры: не оформлено вовсе: 2"]},
    )
    base.update(extra)
    return SimpleNamespace(**base)


class TestLetter:
    def test_тема_несёт_клиента_и_период(self) -> None:
        subject, _body = build_letter(_client(), _report())

        assert "ООО Ромашка" in subject
        assert "11.08.2026" in subject and "18.08.2026" in subject

    def test_текст_несёт_итог_и_действия(self) -> None:
        _subject, body = build_letter(_client(), _report())

        assert "Медосмотры" in body
        assert "Что нужно сделать:" in body
        assert body.strip(), "пустое письмо клиенту хуже неотправленного"

    def test_без_действий_раздел_не_печатается(self) -> None:
        _subject, body = build_letter(_client(), _report(payload={"actions": []}))

        assert "Что нужно сделать:" not in body


@pytest.mark.anyio
class TestGuards:
    async def test_без_адреса_не_отправляем(self) -> None:
        outcome = await send_report_to_client(_client(report_email=None), _report())

        assert outcome.status is ReportSendStatus.NO_EMAIL
        assert "не указан адрес" in outcome.reason

    async def test_адреса_без_согласия_недостаточно(self) -> None:
        """Знать e-mail и иметь право писать — разные вещи."""

        outcome = await send_report_to_client(_client(report_opt_in=False), _report())

        assert outcome.status is ReportSendStatus.NO_CONSENT
        assert "согласия" in outcome.reason

    async def test_пустая_строка_адреса_считается_отсутствием(self) -> None:
        outcome = await send_report_to_client(_client(report_email="   "), _report())

        assert outcome.status is ReportSendStatus.NO_EMAIL

    async def test_причина_отказа_всегда_словами(self) -> None:
        for client in (_client(report_email=None), _client(report_opt_in=False)):
            outcome = await send_report_to_client(client, _report())
            assert outcome.reason.strip(), "молчаливый отказ читается как сбой"
            assert outcome.status is not ReportSendStatus.SENT
