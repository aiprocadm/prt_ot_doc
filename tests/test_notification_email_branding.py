"""Письмо уходит под брендом арендатора (BIZ-52 срез-10, Доп. №1 разд. 52.2).

Проверяем СОБРАННОЕ сообщение, а не намерение: заголовки письма — то место, где
русское имя превращается в крякозябры, а перенос строки роняет отправку целиком.
"""

from __future__ import annotations

from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from app.domains.reseller.mail_identity import build_mail_identity
from app.domains.reseller.white_label import PLATFORM_BRAND, AppBrand
from app.modules.notifications.providers import EmailProvider
from app.modules.notifications.providers.base import NotificationContact


def _settings(**extra) -> SimpleNamespace:
    base = dict(
        notifications_delivery_enabled=True,
        notifications_max_delivery_attempts=3,
        smtp_host="smtp.local",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_from="no-reply@platform.example",
        smtp_use_tls=True,
        admin_email="admin@platform.example",
    )
    base.update(extra)
    return SimpleNamespace(**base)


class _FakeSMTP:
    """Заглушка SMTP: запоминает сообщение вместо отправки по сети."""

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


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch):
    import smtplib

    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


def _brand(**kwargs) -> AppBrand:
    base = dict(
        app_name="Охрана труда «Партнёр»",
        primary_color="222.2 47.4% 11.2%",
        support_email="help@partner.example",
        source="reseller",
    )
    base.update(kwargs)
    return AppBrand(**base)


def _notification(body: str = "Срок обучения истекает.") -> SimpleNamespace:
    return SimpleNamespace(tenant_id="t-1", title="Напоминание", body=body)


def _send(brand: AppBrand, notification=None) -> EmailMessage:
    provider = EmailProvider(_settings())
    provider._send(
        "client@example.com", notification or _notification(), build_mail_identity(brand)
    )
    return _FakeSMTP.sent[-1]


def test_имя_партнёра_видно_в_отправителе():
    msg = _send(_brand())

    # Заголовок хранится закодированным, но читается обратно тем же именем —
    # проверяем именно это, иначе тест закрепил бы крякозябры.
    assert "Охрана труда «Партнёр»" in str(msg["From"])
    assert "no-reply@platform.example" in str(msg["From"])


def test_кириллица_в_отправителе_закодирована_по_стандарту():
    raw = _send(_brand()).as_string()

    # Сырое письмо не должно нести кириллицу байтами: почтовые узлы по пути
    # имеют право на 7 бит, и такое имя доехало бы мусором.
    from_line = next(line for line in raw.splitlines() if line.startswith("From:"))
    assert from_line.isascii()
    assert "=?utf-8?" in from_line.lower()


def test_адрес_отправителя_остаётся_платформенным():
    # Подстановка чужого домена провалила бы SPF и DKIM — письма партнёра ушли
    # бы в спам. Домен партнёра — отдельный пункт 52.2, он не сделан.
    assert "@platform.example" in str(_send(_brand())["From"])
    assert "partner.example" not in str(_send(_brand())["From"])


def test_ответ_уходит_на_почту_партнёра():
    assert str(_send(_brand())["Reply-To"]) == "help@partner.example"


def test_без_почты_поддержки_заголовка_ответа_нет():
    assert _send(_brand(support_email=None))["Reply-To"] is None


def test_тело_подписано_брендом():
    body = _send(_brand()).get_content()

    assert "— Охрана труда «Партнёр»" in body
    assert "Поддержка: help@partner.example" in body


def test_имя_с_переносом_строки_не_роняет_отправку():
    # ГЛАВНАЯ проверка среза: схема бренда переносы пропускает, а заголовок
    # письма — нет. Без чистки одно такое имя лишило бы писем всех клиентов
    # партнёра, и причина («ValueError: Header values may not contain
    # linefeed») никак не связалась бы с настройкой бренда.
    msg = _send(_brand(app_name="Партнёр\nBcc: chuzhoy@example.com"))

    assert msg["Bcc"] is None
    assert "Партнёр" in str(msg["From"])


def test_прямой_клиент_платформы_получает_платформенную_подпись():
    msg = _send(PLATFORM_BRAND)

    assert PLATFORM_BRAND.app_name in str(msg["From"])
    assert msg["Reply-To"] is None


def test_тема_письма_не_трогается():
    # Бренд подменяет отправителя и подпись; тема — текст уведомления, и
    # приписка к ней сломала бы группировку писем в почтовых клиентах.
    assert str(_send(_brand())["Subject"]) == "Напоминание"


@pytest.mark.asyncio
async def test_сбой_чтения_бренда_не_отменяет_письмо(monkeypatch):
    # Письмо без партнёрского имени хуже, чем с ним, но недоставленное — хуже
    # обоих. Заглушка уведомления намеренно без tenant_id: так падает обращение
    # к бренду, и мы видим именно деградацию, а не отказ.
    provider = EmailProvider(_settings())
    result = await provider.deliver(
        notification=SimpleNamespace(title="t", body="b"),
        contact=NotificationContact(email="client@example.com"),
    )

    assert result.delivered
    assert PLATFORM_BRAND.app_name in str(_FakeSMTP.sent[-1]["From"])
