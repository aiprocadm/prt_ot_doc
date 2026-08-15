"""Свои лимиты и свой расход (BIZ-52 срез-15, Доп. №1 разд. 52.4).

Срез-13 показал партнёру расход КЛИЕНТОВ. Своего он по-прежнему не видит: в
собственную область партнёр не входит (решение среза-2 — иначе он мог бы
приостановить сам себя), поэтому его строки нет ни в списке, ни в отчёте о
расходе. Лимиты тоже не показывались: ручка `GET /tenants/me` их отдаёт, но
фронт её не вызывает НИГДЕ.

Партнёр при этом сам живёт на квотах платформы — и должен видеть, сколько у него
осталось, до того как упрётся.

**Лимит без расхода бесполезен.** «10 000 документов в месяц» не отвечает на
вопрос «хватит ли до конца месяца»; отвечает пара «использовано 9 800 из
10 000». Поэтому строка лимита всегда несёт обе величины — либо честно
говорит, что расход не считается.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Мегабайт в байтах. Квота хранится в мегабайтах, расход — в байтах.
BYTES_IN_MB = 1024 * 1024


@dataclass(frozen=True)
class LimitLine:
    """Одна строка «сколько можно и сколько занято»."""

    code: str
    title: str
    #: Предел. `None` — предела нет.
    limit: int | None
    #: Израсходовано. `None` — НЕ СЧИТАЕТСЯ (не то же, что ноль).
    used: int | None
    #: Единица измерения для человека.
    unit: str

    @property
    def measured(self) -> bool:
        return self.used is not None

    @property
    def remaining(self) -> int | None:
        """Остаток. `None`, если расход не считается или предела нет."""

        if self.limit is None or self.used is None:
            return None
        return max(self.limit - self.used, 0)

    @property
    def exhausted(self) -> bool:
        """Предел выбран полностью.

        Отдельный признак, а не «остаток равен нулю»: остаток `None` означает
        «неизвестно», и путать это с «всё израсходовано» нельзя.
        """

        remaining = self.remaining
        return remaining is not None and remaining == 0


def build_limit_lines(
    *,
    max_doc_generations_per_month: int | None,
    max_storage_mb: int | None,
    monthly_edo_outgoing: int | None,
    max_parallel_jobs: int | None,
    doc_generations_used: int,
    storage_bytes_used: int,
) -> list[LimitLine]:
    """Собрать строки лимитов из квот и расхода.

    Расход берётся из тех же источников, что и отчёт по клиентам (срез-13):
    третья правда о том, сколько израсходовано, разошлась бы с первыми двумя.

    `monthly_edo_outgoing` идёт с `used=None`: квота есть, а счётчик ЭДО не
    увеличивает никто (провайдер отправки не реализован). Ноль здесь означал бы
    «ЭДО не пользуются» вместо «мы это не считаем».

    `max_parallel_jobs` — предел ОДНОВРЕМЕННОСТИ, а не месячный расход: рядом с
    ним нет величины «использовано за период», и выдумывать её нельзя.
    """

    return [
        LimitLine(
            code="doc_generations",
            title="Документы за месяц",
            limit=max_doc_generations_per_month,
            used=doc_generations_used,
            unit="шт.",
        ),
        LimitLine(
            code="storage",
            title="Хранилище",
            limit=(max_storage_mb * BYTES_IN_MB) if max_storage_mb is not None else None,
            used=storage_bytes_used,
            unit="байт",
        ),
        LimitLine(
            code="edo_outgoing",
            title="Исходящие ЭДО за месяц",
            limit=monthly_edo_outgoing,
            used=None,
            unit="шт.",
        ),
        LimitLine(
            code="parallel_jobs",
            title="Одновременных задач",
            limit=max_parallel_jobs,
            used=None,
            unit="шт.",
        ),
    ]
