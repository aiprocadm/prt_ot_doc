"""Сторож: домен партнёра подтверждается, выручка считается (BIZ-52, срез-189).

ЧТО БЫЛО. Два остатка строки, оба выглядели «внешними»:

* 52.2 «домен и поддомен партнёра — DNS и сертификаты вне кода»;
* 52.4 «выручка партнёра упирается в отсутствие модели цен — партнёр назначает
  цену сам, но храним её негде».

У обоих была код-часть, и в обоих случаях её отсутствие означало настоящую
проблему, а не недоделку.

**Домен.** Без подтверждения владения партнёр заявляет ЧУЖОЙ домен, и платформа
начинает отдавать под ним его бренд и его страницу входа. Это подмена сайта
чужими руками.

**Выручка.** Без срока действия у цены отчёт за прошлый квартал считался бы по
сегодняшней цене — то есть повышение переписывало бы прошлое. Партнёр по этому
отчёту выставляет счета.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_reseller_domains_and_revenue.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.domains.reseller import domains, revenue


class TestДомен:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Partner.Example", "partner.example"),
            ("partner.example.", "partner.example"),
            ("  PARTNER.example  ", "partner.example"),
            ("https://partner.example/login", "partner.example"),
            ("lk.partner.example", "lk.partner.example"),
        ],
    )
    def test_приводится_к_каноническому_виду(self, raw: str, expected: str) -> None:
        """Две записи одного домена означали бы, что глобальной уникальности нет."""

        assert domains.normalize_domain(raw) == expected

    @pytest.mark.parametrize(
        "raw", ["", None, "не домен", "partner", "-bad.example", "пример.рф ", "a" * 300]
    )
    def test_негодное_отвергается(self, raw) -> None:
        with pytest.raises(domains.DomainError):
            domains.normalize_domain(raw)

    def test_запись_ищется_под_отдельной_меткой(self) -> None:
        """В корне у партнёра уже лежат чужие TXT-записи — туда лезть нельзя."""

        assert domains.expected_record("partner.example") == "_ptd-verify.partner.example"

    def test_подтверждение_срабатывает_на_нужном_значении(self) -> None:
        token = domains.new_token()
        result = domains.check(
            "partner.example",
            token,
            resolve_txt=lambda name: [f"ptd-verify={token}"],
        )
        assert result.verified

    def test_соседние_записи_не_мешают(self) -> None:
        """У домена уже есть SPF и проверки других служб — это норма."""

        token = domains.new_token()
        result = domains.check(
            "partner.example",
            token,
            resolve_txt=lambda name: [
                "v=spf1 include:example.com ~all",
                f'"ptd-verify={token}"',
                "google-site-verification=xyz",
            ],
        )
        assert result.verified

    def test_чужое_слово_не_подтверждает(self) -> None:
        """ГЛАВНАЯ ПРОВЕРКА: подтверждение чужого домена = подмена сайта."""

        result = domains.check(
            "partner.example",
            domains.new_token(),
            resolve_txt=lambda name: ["ptd-verify=someone-elses-token"],
        )
        assert not result.verified
        assert "нет нужного значения" in result.detail

    def test_записи_нет_и_dns_не_ответил_это_разные_сообщения(self) -> None:
        """«Записи нет» человек чинит сам; «DNS не ответил» значит повторить позже."""

        missing = domains.check("partner.example", "t", resolve_txt=lambda name: [])
        assert "не найдено" in missing.detail

        def _boom(name: str):
            raise TimeoutError("no answer")

        broken = domains.check("partner.example", "t", resolve_txt=_boom)
        assert "DNS не ответил" in broken.detail
        assert "Повторите позже" in broken.detail

    def test_слово_одноразовое_и_длинное(self) -> None:
        a, b = domains.new_token(), domains.new_token()
        assert a != b
        assert len(a) == 32


@dataclass
class _Price:
    client_tenant_id: str
    amount_minor: int
    period: str
    valid_from: date
    valid_to: date | None = None
    currency: str = "RUB"


class TestВыручка:
    def test_цена_прошлого_периода_не_переписывается_новой(self) -> None:
        """ГЛАВНАЯ ПРОВЕРКА: повышение цены не меняет отчёт за прошлый квартал."""

        prices = [
            _Price("c1", 300000, "month", date(2026, 1, 1), date(2026, 6, 30)),
            _Price("c1", 500000, "month", date(2026, 7, 1)),
        ]
        first_half = revenue.build_report(prices, since=date(2026, 1, 1), until=date(2026, 6, 30))
        # Полгода по 3000 рублей, а не по 5000.
        assert first_half["total_minor"] == 300000 * 6

    def test_период_приводится_к_месяцу(self) -> None:
        assert revenue.monthly_minor(1200000, "year") == 100000
        assert revenue.monthly_minor(300000, "quarter") == 100000
        assert revenue.monthly_minor(100000, "month") == 100000

    def test_неизвестный_период_это_ошибка(self) -> None:
        """Тихое «считаем как месяц» дало бы неверный счёт клиенту."""

        with pytest.raises(ValueError, match="Неизвестный период"):
            revenue.monthly_minor(100, "decade")

    def test_остаток_отбрасывается_вниз(self) -> None:
        """Недосчитать копейку честнее, чем начислить лишнюю."""

        assert revenue.monthly_minor(100, "quarter") == 33

    def test_строка_вне_окна_не_попадает_в_отчёт(self) -> None:
        prices = [_Price("c1", 100000, "month", date(2025, 1, 1), date(2025, 12, 31))]
        report = revenue.build_report(prices, since=date(2026, 1, 1), until=date(2026, 3, 31))
        assert report["total_minor"] == 0
        assert report["lines"] == []

    def test_другая_валюта_не_складывается_но_и_не_замалчивается(self) -> None:
        """Сложить рубли с тенге значило бы выдать бессмысленное число.

        Но и промолчать нельзя: партнёр решил бы, что клиента забыли завести.
        """

        prices = [
            _Price("c1", 100000, "month", date(2026, 1, 1)),
            _Price("c2", 100000, "month", date(2026, 1, 1), currency="KZT"),
        ]
        report = revenue.build_report(prices, since=date(2026, 1, 1), until=date(2026, 1, 31))
        assert report["total_minor"] == 100000
        assert report["skipped_other_currency"] == ["KZT"]

    def test_строки_упорядочены_по_убыванию_суммы(self) -> None:
        prices = [
            _Price("small", 10000, "month", date(2026, 1, 1)),
            _Price("big", 900000, "month", date(2026, 1, 1)),
        ]
        report = revenue.build_report(prices, since=date(2026, 1, 1), until=date(2026, 1, 31))
        assert [line["client_tenant_id"] for line in report["lines"]] == ["big", "small"]

    def test_действующая_до_сих_пор_цена_считается_до_конца_окна(self) -> None:
        prices = [_Price("c1", 100000, "month", date(2026, 1, 1), None)]
        report = revenue.build_report(prices, since=date(2026, 1, 1), until=date(2026, 12, 31))
        assert report["total_minor"] == 100000 * 12
