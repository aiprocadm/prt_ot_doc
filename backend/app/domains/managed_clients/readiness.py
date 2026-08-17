"""BIZ-51 срез-5 (Доп. №1 разд. 51.3): эталон соответствия и светофор клиента.

ТЗ: «для каждого долгосрочного клиента — „эталон соответствия“: что у него
должно быть; система непрерывно сравнивает факт с эталоном и показывает
разрыв». Ключевое отличие от «Центра внимания» (BIZ-49): тот показывает
ПРОСРОЧКИ существующих записей, а эталон — ОТСУТСТВИЕ положенного. Сотрудник,
которому по норме должности положен медосмотр, а записи нет вовсе, в «Центре
внимания» не появится никогда: там нечему просрочиваться.

Правила чистые (без базы): цвет светофора решает судьбу клиентского отчёта и
абонплаты, его надо уметь проверить построчно.

## Три решения, без которых светофор врал бы

**1. Зелёное — только доказанное.** Направление зелёное, когда эталон ЗАДАН
(у должностей клиента есть нормы) и всё положенное действует. Пустой эталон —
не зелёный, а «эталон не задан»: «у клиента нет норм» и «у клиента всё есть» —
разные утверждения, и красить первое зелёным значило бы продать тишину как
благополучие (тот же довод, что `not_measured` в расходе BIZ-52 среза-13).

**2. Дисциплины без поимённого учёта не красятся вовсе.** ТЗ называет шесть
дисциплин (ОТ/ПБ/ПромБез/Экология/ГО-ЧС/БДД), но поимённые нормы в системе
есть только у медосмотров и СИЗ. Остальные отдаются с честным «не ведётся» и
причиной — жёлтый или зелёный по ним был бы выдумкой.

**3. «Не было вовсе» и «было, но не действует» — разные разрывы.** Оба
красные, но специалист по ним работает по-разному: первый — организовать с
нуля, второй — продлить или довыдать. В расшифровке они названы отдельными
числами.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

__all__ = [
    "Direction",
    "DirectionCounts",
    "DirectionReadiness",
    "TrafficLight",
    "MEASURED_DIRECTIONS",
    "UNMEASURED_DIRECTIONS",
    "build_directions",
    "evaluate_direction",
    "worst_light",
]


class TrafficLight(str, enum.Enum):
    """Цвет направления. ``not_measured`` — отдельное состояние, не цвет:

    зелёный утверждает «всё положенное действует», и говорить это без
    эталона нельзя.
    """

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    NOT_MEASURED = "not_measured"


class Direction(str, enum.Enum):
    """Направления светофора: измеримые сегодня + дисциплины ТЗ."""

    MEDICAL = "medical"
    PPE = "ppe"
    TRAINING = "training"
    FIRE_SAFETY = "fire_safety"
    INDUSTRIAL_SAFETY = "industrial_safety"
    ECOLOGY = "ecology"
    CIVIL_DEFENSE = "civil_defense"
    ROAD_SAFETY = "road_safety"


DIRECTION_TITLES: dict[Direction, str] = {
    Direction.MEDICAL: "Медосмотры",
    Direction.PPE: "СИЗ",
    Direction.TRAINING: "Обучение",
    Direction.FIRE_SAFETY: "Пожарная безопасность",
    Direction.INDUSTRIAL_SAFETY: "Промышленная безопасность",
    Direction.ECOLOGY: "Экология",
    Direction.CIVIL_DEFENSE: "ГО и ЧС",
    Direction.ROAD_SAFETY: "БДД",
}

#: Направления, по которым в системе есть поимённые данные.
MEASURED_DIRECTIONS: tuple[Direction, ...] = (
    Direction.MEDICAL,
    Direction.PPE,
    Direction.TRAINING,
)

#: Дисциплины без поимённого учёта — отдаются с причиной, не с цветом.
UNMEASURED_DIRECTIONS: dict[Direction, str] = {
    Direction.FIRE_SAFETY: "Поимённый учёт пожарной безопасности в системе не ведётся",
    Direction.INDUSTRIAL_SAFETY: "Поимённый учёт промышленной безопасности в системе не ведётся",
    Direction.ECOLOGY: "Поимённый учёт экологии в системе не ведётся",
    Direction.CIVIL_DEFENSE: "Поимённый учёт ГО и ЧС в системе не ведётся",
    Direction.ROAD_SAFETY: "Поимённый учёт БДД в системе не ведётся",
}


@dataclass(frozen=True)
class DirectionCounts:
    """Числа одного направления — то, что собрал сервис.

    ``required`` — сколько пар «сотрудник × норма» задаёт эталон;
    ``missing`` — положенного не было вовсе; ``lapsed`` — оформлено, но не действует или не хватает;
    ``expiring`` — действует, но истекает в горизонте.
    """

    required: int = 0
    missing: int = 0
    lapsed: int = 0
    expiring: int = 0


@dataclass(frozen=True)
class DirectionReadiness:
    direction: Direction
    title: str
    light: TrafficLight
    reason: str
    counts: DirectionCounts = field(default_factory=DirectionCounts)


def evaluate_direction(counts: DirectionCounts) -> tuple[TrafficLight, str]:
    """Цвет и расшифровка по числам. Расшифровка обязательна:

    ТЗ просит «зелёное/жёлтое/красное С РАСШИФРОВКОЙ» — цвет без слов
    возвращает специалиста к гаданию, зачем он красный.
    """

    if counts.required == 0:
        return (
            TrafficLight.NOT_MEASURED,
            "Эталон не задан: у должностей клиента нет норм",
        )
    gaps = counts.missing + counts.lapsed
    if gaps > 0:
        parts = []
        if counts.missing:
            parts.append(f"не оформлено вовсе: {counts.missing}")
        if counts.lapsed:
            parts.append(f"истекло или не хватает: {counts.lapsed}")
        return TrafficLight.RED, "Разрывы с эталоном — " + ", ".join(parts)
    if counts.expiring > 0:
        return (
            TrafficLight.YELLOW,
            f"Всё положенное есть, но истекает в ближайшее время: {counts.expiring}",
        )
    return TrafficLight.GREEN, f"Всё положенное действует ({counts.required})"


def training_readiness(overdue: int) -> DirectionReadiness:
    """Обучение — направление без эталона: норм обучения в системе нет.

    Система видит только просрочки НАЗНАЧЕННОГО обучения. Просрочка красит
    красным, а «просрочек нет» даёт не зелёный, а честное «эталон не задан»:
    неназначенное обучение система не увидит.
    """

    if overdue > 0:
        return DirectionReadiness(
            direction=Direction.TRAINING,
            title=DIRECTION_TITLES[Direction.TRAINING],
            light=TrafficLight.RED,
            reason=f"Просрочено назначенное обучение: {overdue}",
            counts=DirectionCounts(required=overdue, lapsed=overdue),
        )
    return DirectionReadiness(
        direction=Direction.TRAINING,
        title=DIRECTION_TITLES[Direction.TRAINING],
        light=TrafficLight.NOT_MEASURED,
        reason=(
            "Эталон обучения не задан: система видит только просрочки "
            "назначенного, неназначенное ей не видно"
        ),
    )


def build_directions(
    *,
    medical: DirectionCounts,
    ppe: DirectionCounts,
    training_overdue: int,
) -> list[DirectionReadiness]:
    """Полный светофор клиента: измеримое + дисциплины с причиной.

    Порядок фиксированный (как в ТЗ), а не «красное сверху»: светофор читают
    регулярно, и скачущие местами строки мешают сравнивать неделю с неделей.
    """

    rows: list[DirectionReadiness] = []
    for direction, counts in ((Direction.MEDICAL, medical), (Direction.PPE, ppe)):
        light, reason = evaluate_direction(counts)
        rows.append(
            DirectionReadiness(
                direction=direction,
                title=DIRECTION_TITLES[direction],
                light=light,
                reason=reason,
                counts=counts,
            )
        )
    rows.append(training_readiness(training_overdue))
    for direction, reason in UNMEASURED_DIRECTIONS.items():
        rows.append(
            DirectionReadiness(
                direction=direction,
                title=DIRECTION_TITLES[direction],
                light=TrafficLight.NOT_MEASURED,
                reason=reason,
            )
        )
    return rows


def worst_light(rows: list[DirectionReadiness]) -> TrafficLight:
    """Итог клиента — по худшему ИЗМЕРЕННОМУ направлению.

    ``not_measured`` в итог не входит: клиент с зелёными медосмотрами и СИЗ
    не должен выглядеть неизвестным из-за дисциплин, которых в системе нет.
    Если не измерено НИЧЕГО — итог честно ``not_measured``.
    """

    measured = [r.light for r in rows if r.light is not TrafficLight.NOT_MEASURED]
    if not measured:
        return TrafficLight.NOT_MEASURED
    for light in (TrafficLight.RED, TrafficLight.YELLOW):
        if light in measured:
            return light
    return TrafficLight.GREEN
