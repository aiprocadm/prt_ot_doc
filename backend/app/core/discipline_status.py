"""Светофор соответствия по дисциплинам — правила, общие для всего продукта.

Правила родились в светофоре клиента (BIZ-51 срез-5,
``domains/managed_clients/readiness.py``) и там же жили. Карточка площадки 360°
(BIZ-54-57 срез-3, Доп. №1 разд. 57.1) показывает тот же светофор, но по людям
одной площадки — и если бы она импортировала правила из домена аутсорсинга, то
«площадка зависела бы от аутсорсинга»: связь, которой в продукте нет. Поэтому
правила переехали в ядро тем же ходом, что и словарь дисциплин в срезе-1, а
светофор клиента берёт их отсюда под своими прежними именами.

Правила чистые (без базы): цвет решает судьбу клиентского отчёта и абонплаты,
его надо уметь проверить построчно.

## Три решения, без которых светофор врал бы

**1. Зелёное — только доказанное.** Дисциплина зелёная, когда эталон ЗАДАН (у
должностей есть нормы) и всё положенное действует. Пустой эталон — не зелёный,
а «эталон не задан»: «норм нет» и «всё есть» — разные утверждения, и красить
первое зелёным значило бы продать тишину как благополучие (тот же довод, что
``not_measured`` в расходе BIZ-52 среза-13).

**2. Дисциплины без поимённого учёта не красятся вовсе.** ТЗ называет шесть
дисциплин (ОТ/ПБ/ПромБез/Экология/ГО-ЧС/БДД), но поимённые нормы в системе есть
только у медосмотров и СИЗ. Остальные отдаются с честным «не ведётся» и
причиной — жёлтый или зелёный по ним был бы выдумкой.

**3. «Не было вовсе» и «было, но не действует» — разные разрывы.** Оба красные,
но специалист по ним работает по-разному: первый — организовать с нуля, второй
— продлить или довыдать. В расшифровке они названы отдельными числами.

**4. БДД: удостоверение водителя — факт, а не эталон (срез-64).** У допущенного
водителя есть один поимённый срок — удостоверение, и истекшее удостоверение
красит БДД красным так же честно, как просроченное обучение красит
«Обучение». Но зелёным БДД не бывает: действующее удостоверение не значит
«всё положенное по БДД действует» — предрейсовые, стажировки и инструктажи
эталоном не заданы. Это тот же приём, что у обучения: просрочка — красный,
её отсутствие — не зелёный, а «не измеряется» с фактом в расшифровке.

**5. ПБ: сроки объекта — факт, а не эталон (срез-82).** У площадки есть свои
сроки пожарной безопасности — перезарядка и поверка средств защиты, плановая
тренировка, пересмотр документов, — и просроченный срок красит ПБ красным так
же честно, как истёкшее удостоверение красит БДД. Но зелёной ПБ не бывает:
сколько средств защиты, документов и тренировок объекту ПОЛОЖЕНО, платформа
не судит (признаков применимости норм у площадки нет), и «сроки в порядке»
не значит «всё положенное есть». Средства без единой записи о работах и
давность последней тренировки — факты в расшифровке, цвет они не трогают.

**6. ПБ: противопожарные инструктажи людей — в цвет (срез-83).** Истёкший
противопожарный инструктаж или ПТМ — поимённый срок, как удостоверение
водителя у БДД, и красит ПБ красным наравне с непроверенным огнетушителем
(так его и считает сводка готовности модуля, разд. 54.1 «контроль сроков»).
Считается человек × вид по самой поздней дате действия, а не каждая запись:
старая запись, перекрытая свежим повторным инструктажем, — не нарушение.
Сколько людям ПОЛОЖЕНО инструктажей, платформа не судит — поэтому и с
действующими инструктажами ПБ не зелёная, а «не измеряется» с фактом.

**7. ПБ у одного человека — только его инструктажи (срез-84).** Карточка
сотрудника считает строку ПБ той же формулой, но без объектов: средства
защиты, тренировки и документы — сроки площадки, у человека их нет, и
говорить «проведённых тренировок нет» про сварщика было бы ложью. Без
объектов и причина другая (``FIRE_SAFETY_PERSON_REASON``): не «эталон по
объекту не ведётся», а «сколько инструктажей человеку положено, не судится».
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import date

from app.core.disciplines import (
    DISCIPLINE_TITLES,
    UNMEASURED_DISCIPLINES,
    Discipline,
)

__all__ = [
    "DisciplineCounts",
    "DisciplineStatus",
    "FIRE_SAFETY_PERSON_REASON",
    "FireSafetyNumbers",
    "RoadSafetyNumbers",
    "TrafficLight",
    "build_discipline_statuses",
    "evaluate_counts",
    "fire_safety_status",
    "road_safety_status",
    "training_status",
    "with_extra_reason",
    "worst_light",
]


class TrafficLight(str, enum.Enum):
    """Цвет дисциплины. ``not_measured`` — отдельное состояние, не цвет:

    зелёный утверждает «всё положенное действует», и говорить это без эталона
    нельзя.
    """

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    NOT_MEASURED = "not_measured"


@dataclass(frozen=True)
class DisciplineCounts:
    """Числа одной дисциплины — то, что собрал сервис.

    ``required`` — сколько пар «сотрудник × норма» задаёт эталон;
    ``missing`` — положенного не было вовсе; ``lapsed`` — оформлено, но не
    действует или не хватает; ``expiring`` — действует, но истекает в горизонте.
    """

    required: int = 0
    missing: int = 0
    lapsed: int = 0
    expiring: int = 0


@dataclass(frozen=True)
class DisciplineStatus:
    discipline: Discipline
    title: str
    light: TrafficLight
    reason: str
    counts: DisciplineCounts = field(default_factory=DisciplineCounts)


def evaluate_counts(counts: DisciplineCounts) -> tuple[TrafficLight, str]:
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


def training_status(overdue: int) -> DisciplineStatus:
    """Обучение — дисциплина без эталона: норм обучения в системе нет.

    Система видит только просрочки НАЗНАЧЕННОГО обучения. Просрочка красит
    красным, а «просрочек нет» даёт не зелёный, а честное «эталон не задан»:
    неназначенное обучение система не увидит.
    """

    if overdue > 0:
        return DisciplineStatus(
            discipline=Discipline.TRAINING,
            title=DISCIPLINE_TITLES[Discipline.TRAINING],
            light=TrafficLight.RED,
            reason=f"Просрочено назначенное обучение: {overdue}",
            counts=DisciplineCounts(required=overdue, lapsed=overdue),
        )
    return DisciplineStatus(
        discipline=Discipline.TRAINING,
        title=DISCIPLINE_TITLES[Discipline.TRAINING],
        light=TrafficLight.NOT_MEASURED,
        reason=(
            "Эталон обучения не задан: система видит только просрочки "
            "назначенного, неназначенное ей не видно"
        ),
    )


@dataclass(frozen=True)
class RoadSafetyNumbers:
    """Водительские удостоверения по набору людей — поимённый факт БДД (срез-64).

    Считаются ТОЛЬКО допущенные к управлению — то же правило, что у источника
    ``road_safety_driver`` общего календаря и у готовности модуля БДД. Пустая
    дата — «сведений нет», не просрочка (бессрочных удостоверений не бывает,
    но «не знаем» и «истекло» — разные утверждения).
    """

    #: допущенных водителей среди этих людей
    drivers: int = 0
    #: удостоверение истекло
    expired: int = 0
    #: действует, но истекает в горизонте
    expiring: int = 0
    #: срок не указан — сведений нет
    without_due: int = 0
    #: ближайший срок среди действующих — карточке одного человека нужна дата
    next_due: date | None = None


def road_safety_status(numbers: RoadSafetyNumbers) -> DisciplineStatus:
    """БДД по удостоверениям: просрочка — красный, остальное — не зелёный.

    Без водителей — прежняя причина словаря: эталона БДД по должностям нет,
    и у людей без удостоверения сравнивать не с чем. С водителями факт
    называется в расшифровке (дата — когда водитель один), но цвет выше
    жёлтого не поднимается: см. решение 4 в докстринге модуля.
    """

    base = UNMEASURED_DISCIPLINES[Discipline.ROAD_SAFETY]
    title = DISCIPLINE_TITLES[Discipline.ROAD_SAFETY]
    counts = DisciplineCounts(
        required=numbers.drivers, lapsed=numbers.expired, expiring=numbers.expiring
    )
    if numbers.drivers == 0:
        return DisciplineStatus(
            discipline=Discipline.ROAD_SAFETY,
            title=title,
            light=TrafficLight.NOT_MEASURED,
            reason=base,
        )
    no_date = f"; срок не указан: {numbers.without_due}" if numbers.without_due else ""
    if numbers.expired > 0:
        return DisciplineStatus(
            discipline=Discipline.ROAD_SAFETY,
            title=title,
            light=TrafficLight.RED,
            reason=f"Истекло водительское удостоверение: {numbers.expired}{no_date}",
            counts=counts,
        )
    when = f" (до {numbers.next_due.strftime('%d.%m.%Y')})" if numbers.next_due else ""
    if numbers.expiring > 0:
        return DisciplineStatus(
            discipline=Discipline.ROAD_SAFETY,
            title=title,
            light=TrafficLight.YELLOW,
            reason=(
                f"Водительское удостоверение истекает в ближайшее время: "
                f"{numbers.expiring}{when}{no_date}"
            ),
            counts=counts,
        )
    if numbers.without_due == numbers.drivers:
        fact = f"Срок водительского удостоверения не указан: {numbers.without_due}"
    elif numbers.drivers == 1:
        fact = f"Водительское удостоверение действует{when}"
    else:
        fact = f"Водительские удостоверения действуют: {numbers.drivers - numbers.without_due}{no_date}"
    return DisciplineStatus(
        discipline=Discipline.ROAD_SAFETY,
        title=title,
        light=TrafficLight.NOT_MEASURED,
        reason=f"{fact}. {base}",
        counts=counts,
    )


#: Причина «не измеряется» для ПБ ОДНОГО человека (срез-84, решение 7):
#: объектов у него нет, а сколько инструктажей положено — эталона нет.
FIRE_SAFETY_PERSON_REASON: str = (
    "Сколько противопожарных инструктажей и ПТМ человеку положено, "
    "платформа не судит: сравнивать не с чем"
)


@dataclass(frozen=True)
class FireSafetyNumbers:
    """Сроки пожарной безопасности ОДНОГО объекта — факт ПБ (срез-82).

    Считаются так же, как в сводке готовности модуля ПБ
    (``/fire-safety/readiness``): одна формула на сводку и карточку площадки
    (``services/discipline_fire_safety.py``). Средства — только действующие
    (``status == "active"``); тренировка без протокола — срок, проведённая —
    факт; документ без даты пересмотра — бессрочный, не срок.
    """

    #: действующих средств защиты
    units: int = 0
    #: перезарядка просрочена
    overdue_recharge: int = 0
    #: поверка/ТО просрочены
    overdue_inspection: int = 0
    #: перезарядка или поверка в горизонте «скоро»
    due_soon: int = 0
    #: горизонт «скоро» в днях — чтобы число в расшифровке не требовало пояснений
    due_soon_days: int = 30
    #: средств без единой записи о выполненной работе — срок стоит, а
    #: подтвердить его нечем; факт, не просрочка
    without_maintenance: int = 0
    #: тренировок по плану-графику, не проведённых к плановой дате
    overdue_drills: int = 0
    #: назначенных вперёд
    planned_drills: int = 0
    #: дата последней ПРОВЕДЁННОЙ тренировки; None — не проводилась ни разу
    last_drill_on: date | None = None
    #: сколько дней прошло с последней тренировки; интервал нормы не судится
    days_since_last_drill: int | None = None
    #: карточек документов ПБ
    documents: int = 0
    #: у скольких просрочен пересмотр
    overdue_documents: int = 0
    #: противопожарных инструктажей и ПТМ людей, истёкших (человек × вид по
    #: самой поздней дате действия — срез-83, решение 6)
    overdue_briefings: int = 0
    #: истекают в горизонте «скоро»
    briefings_due_soon: int = 0
    #: действуют дольше горизонта — факт, цвет не трогает
    briefings_valid: int = 0
    #: считались ли объекты (средства, тренировки, документы). ``False`` —
    #: только инструктажи людей (карточка сотрудника, срез-84): фактов об
    #: объекте нет, и «тренировок нет» сказать не о чем
    objects_counted: bool = True

    @property
    def overdue(self) -> int:
        """Все просрочки — четыре слагаемых строки «Пожарная безопасность»
        Центра внимания (срез-80) плюс инструктажи людей (срез-83)."""

        return (
            self.overdue_recharge
            + self.overdue_inspection
            + self.overdue_drills
            + self.overdue_documents
            + self.overdue_briefings
        )

    @property
    def expiring(self) -> int:
        """Всё, что истекает в горизонте: сроки средств и инструктажи."""

        return self.due_soon + self.briefings_due_soon

    @property
    def briefings(self) -> int:
        """Сколько инструктажей (человек × вид) вообще со сроком."""

        return self.overdue_briefings + self.briefings_due_soon + self.briefings_valid

    @property
    def has_objects(self) -> bool:
        """Есть ли у объекта хоть что-то по ПБ; без этого — прежняя причина."""

        return bool(
            self.units
            or self.overdue_drills
            or self.planned_drills
            or self.last_drill_on is not None
            or self.documents
            or self.briefings
        )


def _fire_safety_facts(numbers: FireSafetyNumbers) -> list[str]:
    """Факты, которые цвет не трогают, но инспектор спросит первыми."""

    facts: list[str] = []
    if numbers.without_maintenance:
        facts.append(f"средств без записи о работах: {numbers.without_maintenance}")
    if numbers.last_drill_on is not None:
        when = numbers.last_drill_on.strftime("%d.%m.%Y")
        ago = (
            f" ({numbers.days_since_last_drill} дн. назад)"
            if numbers.days_since_last_drill is not None
            else ""
        )
        facts.append(f"последняя тренировка {when}{ago}")
    elif numbers.objects_counted:
        facts.append("проведённых тренировок нет")
    if numbers.planned_drills:
        facts.append(f"тренировок назначено: {numbers.planned_drills}")
    if numbers.briefings_valid:
        facts.append(f"противопожарных инструктажей действует: {numbers.briefings_valid}")
    return facts


def fire_safety_status(numbers: FireSafetyNumbers) -> DisciplineStatus:
    """ПБ по срокам объекта: просрочка — красный, остальное — не зелёный.

    Без средств, тренировок и документов — прежняя причина словаря. С ними
    просроченный срок красит красным, срок в горизонте — жёлтым, порядок в
    сроках — «не измеряется» с фактом: см. решение 5 в докстринге модуля.
    """

    base = (
        UNMEASURED_DISCIPLINES[Discipline.FIRE_SAFETY]
        if numbers.objects_counted
        else FIRE_SAFETY_PERSON_REASON
    )
    title = DISCIPLINE_TITLES[Discipline.FIRE_SAFETY]
    if not numbers.has_objects:
        return DisciplineStatus(
            discipline=Discipline.FIRE_SAFETY,
            title=title,
            light=TrafficLight.NOT_MEASURED,
            reason=base,
        )
    counts = DisciplineCounts(
        required=numbers.units + numbers.briefings,
        lapsed=numbers.overdue,
        expiring=numbers.expiring,
    )
    facts = "; ".join(_fire_safety_facts(numbers))
    # у человека без действующих инструктажей фактов нет — хвост пустой
    tail = f"; {facts}" if facts else ""
    if numbers.overdue > 0:
        parts = _named_amounts(
            ("перезарядка средств защиты", numbers.overdue_recharge),
            ("поверка/ТО", numbers.overdue_inspection),
            ("тренировки", numbers.overdue_drills),
            ("пересмотр документов", numbers.overdue_documents),
            ("противопожарные инструктажи", numbers.overdue_briefings),
        )
        return DisciplineStatus(
            discipline=Discipline.FIRE_SAFETY,
            title=title,
            light=TrafficLight.RED,
            reason=f"Просрочено по ПБ — {parts}{tail}",
            counts=counts,
        )
    if numbers.expiring > 0:
        parts = _named_amounts(
            ("перезарядка или поверка средств защиты", numbers.due_soon),
            ("противопожарные инструктажи", numbers.briefings_due_soon),
        )
        return DisciplineStatus(
            discipline=Discipline.FIRE_SAFETY,
            title=title,
            light=TrafficLight.YELLOW,
            reason=f"Истекает по ПБ в ближайшие {numbers.due_soon_days} дн. — {parts}{tail}",
            counts=counts,
        )
    if not numbers.objects_counted:
        # у человека объектов нет — только его инструктажи, и они действуют
        return DisciplineStatus(
            discipline=Discipline.FIRE_SAFETY,
            title=title,
            light=TrafficLight.NOT_MEASURED,
            reason=f"Противопожарных инструктажей действует: {numbers.briefings_valid}. {base}",
            counts=counts,
        )
    return DisciplineStatus(
        discipline=Discipline.FIRE_SAFETY,
        title=title,
        light=TrafficLight.NOT_MEASURED,
        reason=(
            f"Сроки ПБ не просрочены (средств защиты: {numbers.units}, "
            f"документов: {numbers.documents}); {facts}. {base}"
        ),
        counts=counts,
    )


def _named_amounts(*pairs: tuple[str, int]) -> str:
    """«перезарядка: 1, тренировки: 2» — только ненулевые, в заданном порядке."""

    return ", ".join(f"{label}: {amount}" for label, amount in pairs if amount)


def build_discipline_statuses(
    *,
    medical: DisciplineCounts,
    ppe: DisciplineCounts,
    training_overdue: int,
    road_safety: RoadSafetyNumbers | None = None,
    fire_safety: FireSafetyNumbers | None = None,
) -> list[DisciplineStatus]:
    """Полный светофор: измеримое + дисциплины с причиной.

    Порядок фиксированный (как в ТЗ), а не «красное сверху»: светофор читают
    регулярно, и скачущие местами строки мешают сравнивать неделю с неделей.

    ``road_safety`` и ``fire_safety`` необязательны: кто удостоверения или
    сроки объекта не считал (светофор клиента, карточка сотрудника), получает
    прежнюю причину словаря, а не выдуманные нули.
    """

    rows: list[DisciplineStatus] = []
    for discipline, counts in (
        (Discipline.MEDICAL, medical),
        (Discipline.PPE, ppe),
    ):
        light, reason = evaluate_counts(counts)
        rows.append(
            DisciplineStatus(
                discipline=discipline,
                title=DISCIPLINE_TITLES[discipline],
                light=light,
                reason=reason,
                counts=counts,
            )
        )
    rows.append(training_status(training_overdue))
    for discipline, reason in UNMEASURED_DISCIPLINES.items():
        if discipline is Discipline.ROAD_SAFETY and road_safety is not None:
            rows.append(road_safety_status(road_safety))
            continue
        if discipline is Discipline.FIRE_SAFETY and fire_safety is not None:
            rows.append(fire_safety_status(fire_safety))
            continue
        rows.append(
            DisciplineStatus(
                discipline=discipline,
                title=DISCIPLINE_TITLES[discipline],
                light=TrafficLight.NOT_MEASURED,
                reason=reason,
            )
        )
    return rows


def with_extra_reason(
    rows: list[DisciplineStatus], additions: dict[Discipline, str]
) -> list[DisciplineStatus]:
    """Дописать к расшифровке дисциплины наблюдение, НЕ трогая цвет.

    Нужно карточке площадки: к площадке привязаны наряды-допуски на огневые
    работы, и это факт про пожарную безопасность — но факт не отвечает на
    вопрос «всё ли положенное действует», поэтому цвет остаётся прежним.
    Перекрасить дисциплину по наличию документов значило бы выдать активность
    за соответствие.
    """

    out: list[DisciplineStatus] = []
    for row in rows:
        extra = additions.get(row.discipline)
        out.append(replace(row, reason=f"{row.reason}. {extra}") if extra else row)
    return out


def worst_light(rows: list[DisciplineStatus]) -> TrafficLight:
    """Итог — по худшей ИЗМЕРЕННОЙ дисциплине.

    ``not_measured`` в итог не входит: объект с зелёными медосмотрами и СИЗ не
    должен выглядеть неизвестным из-за дисциплин, которых в системе нет. Если
    не измерено НИЧЕГО — итог честно ``not_measured``.
    """

    measured = [r.light for r in rows if r.light is not TrafficLight.NOT_MEASURED]
    if not measured:
        return TrafficLight.NOT_MEASURED
    for light in (TrafficLight.RED, TrafficLight.YELLOW):
        if light in measured:
            return light
    return TrafficLight.GREEN
