"""Сторож: SMS — настоящий второй канал, а не заглушка (SEC-68, срез-186).

ЧТО БЫЛО. Одноразовый код внешнему получателю уходил ровно одним каналом —
почтой. Строка матрицы держала в остатке «SMS как второй канал — внешний
поставщик, вне кода». Поставщика нет, и подключить его значило бы писать новый
код в момент подключения.

ЧТО ПРОВЕРЯЕТСЯ ЗДЕСЬ. Две вещи, и вторая важнее первой:

1. шов работает — сообщение уходит внешней команде (CLI оператора связи);
2. **ненастроенный канал отказывает ЧЕСТНО.** Заглушка, рапортующая об успехе,
   — ровно та ошибка, за которую платформа уже платила: пустые адаптеры
   уверяли, что ведомство приняло данные. «Не настроено» не имеет права
   выглядеть как «отправлено».

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_sms_gateway.py -v``.
"""

from __future__ import annotations

import stat
import sys
from types import SimpleNamespace

import pytest

from app.services import portal_otp_delivery as delivery
from app.services import sms_gateway


def _settings(**over) -> SimpleNamespace:
    base = {"sms_provider": "disabled", "sms_command": "", "sms_command_timeout_seconds": 10.0}
    base.update(over)
    return SimpleNamespace(**base)


def _script(tmp_path, body: str, name: str = "sms.py") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return f"{sys.executable} {path}"


class TestНормализацияНомера:
    """Номера люди пишут как привыкли; формально верный отказ бесполезен."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+79161234567", "+79161234567"),
            ("89161234567", "+79161234567"),
            ("8 (916) 123-45-67", "+79161234567"),
            ("+7 916 123 45 67", "+79161234567"),
            ("79161234567", "+79161234567"),
        ],
    )
    def test_приводится_к_международному_виду(self, raw: str, expected: str) -> None:
        assert sms_gateway.normalize_phone(raw) == expected

    @pytest.mark.parametrize("raw", ["", None, "не телефон", "12345", "+7916123456789012345"])
    def test_не_номер_отвергается(self, raw) -> None:
        assert sms_gateway.normalize_phone(raw) is None


@pytest.mark.asyncio
async def test_ненастроенный_канал_отказывает_честно() -> None:
    """ГЛАВНАЯ ПРОВЕРКА: «не настроено» не притворяется «отправлено»."""

    outcome = await sms_gateway.send_sms(
        phone="+79161234567", text="код 123456", settings=_settings()
    )
    assert not outcome.delivered
    assert outcome.status is sms_gateway.SmsStatus.DISABLED
    assert "не настроена" in outcome.reason


@pytest.mark.asyncio
async def test_сообщение_уходит_внешней_команде(tmp_path) -> None:
    out = tmp_path / "sent.txt"
    command = _script(
        tmp_path,
        "import sys, pathlib\n"
        f"pathlib.Path({str(out)!r}).write_text(sys.argv[1] + '|' + sys.stdin.read())\n",
    )
    outcome = await sms_gateway.send_sms(
        phone="8 916 123-45-67",
        text="Код: 123456",
        settings=_settings(sms_provider="command", sms_command=command),
    )
    assert outcome.delivered, outcome.reason
    # Номер до команды доходит уже приведённым — оператору не нужно гадать.
    assert out.read_text() == "+79161234567|Код: 123456"


@pytest.mark.asyncio
async def test_отказ_оператора_не_выдаётся_за_успех(tmp_path) -> None:
    command = _script(tmp_path, "import sys\nsys.stderr.write('no balance')\nsys.exit(2)")
    outcome = await sms_gateway.send_sms(
        phone="+79161234567",
        text="код",
        settings=_settings(sms_provider="command", sms_command=command),
    )
    assert not outcome.delivered
    assert outcome.status is sms_gateway.SmsStatus.FAILED


@pytest.mark.asyncio
async def test_код_не_утекает_в_текст_ошибки(tmp_path) -> None:
    """Стандартный вывод команды может содержать сам текст с кодом."""

    command = _script(tmp_path, "print('отправлено: код 123456')\nraise SystemExit(1)")
    outcome = await sms_gateway.send_sms(
        phone="+79161234567",
        text="Код: 123456",
        settings=_settings(sms_provider="command", sms_command=command),
    )
    assert "123456" not in outcome.reason


def test_канал_выбирается_видом_получателя() -> None:
    """Отдельного поля «каким каналом слать» нет: ответ уже дан получателем."""

    assert delivery.channel_for("client@example.com") == delivery.EMAIL
    assert delivery.channel_for("+79161234567") == delivery.SMS


def test_готовность_канала_спрашивается_по_отдельности() -> None:
    """Настроенная почта не делает готовым SMS — иначе ссылку выдали бы в никуда."""

    assert sms_gateway.channel_ready(_settings()) is False
    assert sms_gateway.channel_ready(_settings(sms_provider="command", sms_command="x")) is True
    # Провайдер выбран, но команды нет — это не готовность.
    assert sms_gateway.channel_ready(_settings(sms_provider="command")) is False


def test_неизвестный_поставщик_означает_выключено() -> None:
    """Опечатка в имени поставщика не должна тихо включать отправку."""

    assert sms_gateway.provider_name(_settings(sms_provider="megafonn")) == "disabled"
    assert sms_gateway.channel_ready(_settings(sms_provider="megafonn", sms_command="x")) is False


def test_текст_сообщения_короткий() -> None:
    """SMS считают по знакам, длинное режут — код должен уместиться."""

    text = delivery.build_otp_sms("123456", ttl_minutes=10)
    assert "123456" in text
    assert len(text) <= 70
