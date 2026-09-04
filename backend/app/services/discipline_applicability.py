"""Какие дисциплины ПРИМЕНИМЫ у арендатора (BIZ-54-57 срез-54, приёмка §58.3).

Две строки приёмки читаются вместе: «дисциплины включаются/выключаются
feature-флагами по редакции/клиенту» и «карточка объекта 360° показывает
статус по всем ПРИМЕНИМЫМ дисциплинам». То есть применимость — это и есть
выданный модуль: пять дисциплин Доп. №1 заведены продаваемыми модулями
(``app/modules/subscription/registry.py``), медосмотры — модулем «Медосмотры».

До этого среза карточки объекта и сотрудника перечисляли все восемь дисциплин
без оглядки на редакцию: арендатор без «Экологии» видел на каждой площадке и
у каждого человека строку «Экология — не измеряется». Это не статус, а
реклама невыданного модуля, и она разбавляет карточку.

## Правило

* дисциплина без модуля (СИЗ, обучение) — ядро, применима всегда;
* дисциплина с модулем применима, когда модуль ВЫДАН И ВКЛЮЧЁН
  (:func:`~app.core.feature_flags.is_module_enabled`); «продано и выключено»
  и «никогда не выдавалось» здесь равны — на карточке статуса нет ни там, ни там;
* скрытое НЕ молчит: список скрытых дисциплин отдаётся отдельной фразой, и
  экран обязан её показать — иначе семь строк вместо восьми читались бы как
  недоделка.

Итог (``worst_light``) считается по оставшимся строкам: скрытая дисциплина в
любом случае была «не измеряется» и в итог не входила.

## Сводки с фактами (срез-56)

Центр внимания и разрез по дисциплинам считают не статус, а ФАКТЫ: открытые
происшествия и просрочки. Факт не зависит от того, что куплено: ДТП случилось,
даже если модуль БДД выключен. Поэтому там строка скрытой дисциплины убирается
ТОЛЬКО пустая; строка с фактами остаётся, а фраза (:func:`describe_hidden`)
называет обе группы отдельно — «вне редакции» и «модуль выключен, но записи
остались».
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import DisciplineStatus
from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.core.feature_flags import is_module_enabled

__all__ = [
    "ALL_APPLICABLE",
    "DISCIPLINE_MODULE",
    "DisciplineApplicability",
    "collect_applicability",
    "describe_hidden",
    "only_applicable",
]

#: Дисциплина → код продаваемого модуля; ``None`` — ядро, модуля нет.
#: Склад СИЗ (``warehouse``) сюда НЕ входит: он про остатки, а нормы и выдача
#: СИЗ — ядро.
DISCIPLINE_MODULE: dict[Discipline, str | None] = {
    Discipline.MEDICAL: "medical",
    Discipline.PPE: None,
    Discipline.TRAINING: None,
    Discipline.FIRE_SAFETY: "fire_safety",
    Discipline.INDUSTRIAL_SAFETY: "industrial_safety",
    Discipline.ECOLOGY: "ecology",
    Discipline.CIVIL_DEFENSE: "civil_defense",
    Discipline.ROAD_SAFETY: "road_safety",
}

HIDDEN_PREFIX = "Вне редакции арендатора (модуль не выдан или выключен)"
KEPT_SUFFIX = "модуль не выдан или выключен, но открытые записи есть и показаны как факты"


@dataclass(frozen=True)
class DisciplineApplicability:
    """Скрытые дисциплины — в порядке словаря, чтобы фраза читалась одинаково."""

    hidden: tuple[Discipline, ...] = ()

    def applies(self, discipline: Discipline) -> bool:
        return discipline not in self.hidden

    @property
    def hidden_titles(self) -> list[str]:
        return [DISCIPLINE_TITLES[d] for d in self.hidden]

    @property
    def note(self) -> str | None:
        """Одна фраза про скрытое или ``None``, когда скрывать нечего."""

        if not self.hidden:
            return None
        return f"{HIDDEN_PREFIX}: {', '.join(self.hidden_titles)}"


#: Все восемь применимы — для чистых сборок без базы и для тестов правил.
ALL_APPLICABLE = DisciplineApplicability()


async def collect_applicability(session: AsyncSession, tenant_id: str) -> DisciplineApplicability:
    """Спросить у флагов, какие дисциплины арендатору выданы."""

    hidden: list[Discipline] = []
    for discipline in Discipline:
        code = DISCIPLINE_MODULE[discipline]
        if code is None:
            continue
        if not await is_module_enabled(session, tenant_id, code):
            hidden.append(discipline)
    return DisciplineApplicability(hidden=tuple(hidden))


def only_applicable(
    rows: list[DisciplineStatus], applicability: DisciplineApplicability
) -> list[DisciplineStatus]:
    """Оставить строки применимых дисциплин, порядок не менять."""

    return [row for row in rows if applicability.applies(row.discipline)]


def describe_hidden(
    applicability: DisciplineApplicability, *, with_facts: Iterable[Discipline] = ()
) -> str | None:
    """Фраза для сводки фактов: скрытые пустые — «вне редакции», скрытые с
    фактами — названы отдельно, потому что их строки остались."""

    facts = {d for d in with_facts}
    dropped = [d for d in applicability.hidden if d not in facts]
    kept = [d for d in applicability.hidden if d in facts]
    parts: list[str] = []
    if dropped:
        parts.append(f"{HIDDEN_PREFIX}: {', '.join(DISCIPLINE_TITLES[d] for d in dropped)}")
    if kept:
        parts.append(f"{', '.join(DISCIPLINE_TITLES[d] for d in kept)} — {KEPT_SUFFIX}")
    return "; ".join(parts) or None
