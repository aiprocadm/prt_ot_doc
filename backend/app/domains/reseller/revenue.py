"""Выручка партнёра по клиентам (BIZ-52, разд. 52.4).

ЧТО БЫЛО. Остаток строки: «выручка партнёра по клиентам упирается в отсутствие
модели цен — партнёр назначает цену сам (решение среза-8), но храним её негде».
То есть отчёт было НЕ ИЗ ЧЕГО считать: цена существовала только в голове
партнёра.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Цена хранится строкой с СРОКОМ
ДЕЙСТВИЯ (``reseller_prices``), а отчёт складывает цены, действовавшие В
ЗАПРАШИВАЕМОМ ПЕРИОДЕ.

ПОЧЕМУ СРОК ДЕЙСТВИЯ, А НЕ ОДНО ПОЛЕ «ЦЕНА». Перезаписываемая цена переписывает
прошлое: подняли клиенту тариф в сентябре — и отчёт за июль показывает
сентябрьскую сумму. Спорить с таким отчётом невозможно, а партнёр по нему
выставляет счета.

ДЕНЬГИ В КОПЕЙКАХ. Дробные рубли в плавающей точке рано или поздно дают
расхождение на копейку в итоге, и объяснить его нельзя. Приведение к периоду
отчёта делается в целых копейках с остатком вниз: недосчитать копейку честнее,
чем начислить лишнюю.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Во сколько месяцев обходится период. Квартал и год — точные величины, потому
#: что цена назначается «за период», а не «за 90 дней».
PERIOD_MONTHS = {"month": 1, "quarter": 3, "year": 12}


@dataclass(frozen=True)
class RevenueLine:
    """Строка отчёта: сколько партнёр получает с одного клиента."""

    client_tenant_id: str
    amount_minor: int
    currency: str
    period: str
    monthly_minor: int
    months_in_report: int
    total_minor: int

    def as_dict(self) -> dict[str, object]:
        return {
            "client_tenant_id": self.client_tenant_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "period": self.period,
            "monthly_minor": self.monthly_minor,
            "months_in_report": self.months_in_report,
            "total_minor": self.total_minor,
        }


def monthly_minor(amount_minor: int, period: str) -> int:
    """Привести сумму к месяцу. Остаток отбрасывается ВНИЗ (см. шапку)."""

    months = PERIOD_MONTHS.get((period or "month").lower())
    if not months:
        raise ValueError(f"Неизвестный период цены: {period!r}")
    return int(amount_minor) // months


def _overlap_months(valid_from: date, valid_to: date | None, since: date, until: date) -> int:
    """Сколько ПОЛНЫХ месяцев строка действовала внутри окна отчёта.

    Считаем по месяцам, а не по дням: цена назначена за месяц, и дробить её по
    дням значило бы придумать правило, которого нет в договоре.
    """

    start = max(valid_from, since)
    end = min(valid_to or until, until)
    if start > end:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def build_report(prices, *, since: date, until: date, currency: str = "RUB") -> dict[str, object]:
    """Отчёт партнёра за окно ``[since, until]``.

    ``prices`` — строки ``ResellerPrice`` этого партнёра (любые объекты с полями
    ``client_tenant_id``, ``amount_minor``, ``currency``, ``period``,
    ``valid_from``, ``valid_to``).

    Строки в другой валюте НЕ складываются с рублями: смешать их значило бы
    выдать бессмысленное число. Они перечисляются отдельно.
    """

    lines: list[RevenueLine] = []
    skipped_currency: list[str] = []
    for price in prices:
        price_currency = (getattr(price, "currency", currency) or currency).upper()
        if price_currency != currency.upper():
            skipped_currency.append(price_currency)
            continue
        months = _overlap_months(price.valid_from, price.valid_to, since, until)
        if months <= 0:
            continue
        per_month = monthly_minor(price.amount_minor, price.period)
        lines.append(
            RevenueLine(
                client_tenant_id=str(price.client_tenant_id),
                amount_minor=int(price.amount_minor),
                currency=price_currency,
                period=str(price.period),
                monthly_minor=per_month,
                months_in_report=months,
                total_minor=per_month * months,
            )
        )

    lines.sort(key=lambda line: line.total_minor, reverse=True)
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "currency": currency.upper(),
        "clients": len({line.client_tenant_id for line in lines}),
        "total_minor": sum(line.total_minor for line in lines),
        "lines": [line.as_dict() for line in lines],
        # Молчать о пропущенных строках нельзя: партнёр решил бы, что клиента
        # забыли завести, а его просто не с чем складывать.
        "skipped_other_currency": sorted(set(skipped_currency)),
    }


__all__ = ["PERIOD_MONTHS", "RevenueLine", "build_report", "monthly_minor"]
