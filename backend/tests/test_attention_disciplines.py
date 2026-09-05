"""BIZ-54-57 срез-1: словарь дисциплин Центра внимания (Доп. №1 разд. 57.2).

Правила чистые — проверяются без базы. Закрепляется главное:

* КАЖДЫЙ источник агрегатора календаря либо размечен дисциплиной, либо явно
  назван неклассифицированным. Молча пропущенных быть не может: незамеченный
  источник — это записи, которые не попадут ни в один разрез и исчезнут с
  экрана без следа;
* словарь дисциплин ЕДИНСТВЕННЫЙ на продукт: коды и названия в Центре внимания
  и в светофоре клиента (BIZ-51) — один объект, а не две копии;
* у каждой неизмеряемой дисциплины есть причина, а не ноль.
"""

from __future__ import annotations

from app.core.disciplines import (
    ATTENTION_SOURCES,
    DISCIPLINE_TITLES,
    KIND_DISCIPLINES,
    MEASURED_DISCIPLINES,
    PERSON_SCOPED_SOURCES,
    SOURCE_DISCIPLINE,
    SOURCE_KIND_FIELD,
    UNCLASSIFIED_SOURCES,
    UNMEASURED_DISCIPLINES,
    Discipline,
    attention_sources,
    discipline_of,
    discipline_of_event,
    discipline_of_record,
)
from app.services.calendar_aggregator import ALL_SOURCES


class TestCoverage:
    def test_каждый_источник_агрегатора_разобран(self) -> None:
        """Ни один источник не пропущен молча."""

        known = set(SOURCE_DISCIPLINE) | set(UNCLASSIFIED_SOURCES)
        assert set(ALL_SOURCES) == known, (
            "источник агрегатора не размечен и не назван неклассифицированным: "
            f"{set(ALL_SOURCES) - known}"
        )

    def test_размеченное_и_неклассифицированное_не_пересекаются(self) -> None:
        assert not (set(SOURCE_DISCIPLINE) & set(UNCLASSIFIED_SOURCES))

    def test_у_каждого_неклассифицированного_есть_причина(self) -> None:
        for source, reason in UNCLASSIFIED_SOURCES.items():
            assert reason.strip(), f"источник {source} без причины"

    def test_спрашиваем_только_размеченные_источники(self) -> None:
        assert set(ATTENTION_SOURCES) == set(SOURCE_DISCIPLINE)

    def test_персональное_сужение_объявлено_явно(self) -> None:
        """Список источников с поимённым учётом — явный.

        У остальных фильтр по человеку не применяется, и рабочая роль увидела
        бы чужие записи: это утечка персональных данных, а не косметика.

        Правило уточнено разд. 55.3: у сроков разрешений и плановых замеров ПЭК
        человека НЕТ ВООБЩЕ — это задача организации. Поэтому «уметь сузиться»
        обязаны не все размеченные источники, а ровно те, которые мы
        спрашиваем ПРИ сужении.
        """

        assert PERSON_SCOPED_SOURCES <= set(ALL_SOURCES)
        # При сужении до человека спрашиваем только то, что умеет сузиться.
        assert set(attention_sources(person_id="person-1")) <= PERSON_SCOPED_SOURCES
        # Без сужения — всё размеченное, включая общеорганизационные сроки.
        assert set(attention_sources(person_id=None)) == set(SOURCE_DISCIPLINE)

    def test_общеорганизационные_сроки_не_идут_в_личный_список(self) -> None:
        """Сторож против возврата к прежнему правилу.

        Экологические сроки размечены дисциплиной, но человека в них нет:
        попади они в личный список, рабочая роль увидела бы записи, которые
        агрегатор не сумел бы сузить.
        """

        personal = set(attention_sources(person_id="person-1"))
        assert "ecology_permit" not in personal
        assert "ecology_measurement" not in personal
        # срез-57: ЭПБ устройства, учение ГО и документы ТС — тоже про
        # организацию, а не про человека
        assert "industrial_safety_epb" not in personal
        assert "civil_defense_drill" not in personal
        assert "road_safety_vehicle" not in personal
        # срез-59: а водительское удостоверение — про человека, оно в личном
        # списке ЕСТЬ
        assert "road_safety_driver" in personal

    def test_у_дисциплин_разд_57_2_есть_источник_сроков(self) -> None:
        """Разд. 57.2 (срез-57): ЭПБ на ОПО, учения ГО, техосмотр ТС — в центре.

        Раньше три дисциплины (ПромБез, ГО и ЧС, БДД) не имели ни одного
        источника, и их просрочки в центр не попадали никогда. Пожарная
        безопасность до среза-79 своей ТАБЛИЦЫ сроков не имела: её сроки —
        противопожарные инструктажи, и до них источник дотягивается по виду
        записи (срез-58, ``KIND_DISCIPLINES``). Срез-79 добавил ей источник
        по таблице — перезарядка и поверка средств защиты; путь по виду
        инструктажа остался: у ПБ теперь оба.
        """

        assert set(SOURCE_DISCIPLINE.values()) == set(Discipline)
        assert Discipline.FIRE_SAFETY in KIND_DISCIPLINES
        assert SOURCE_DISCIPLINE["fire_safety_equipment"] is Discipline.FIRE_SAFETY

    def test_дисциплина_записи_по_виду_а_не_по_таблице(self) -> None:
        """Срез-58: три исхода ``discipline_of_record`` — и все три разные."""

        assert discipline_of_record("briefing_entry", "fire_ptm") is Discipline.FIRE_SAFETY
        assert discipline_of_record("briefing_entry", "road_pre_trip") is Discipline.ROAD_SAFETY
        assert discipline_of_record("briefing_entry", "repeat") is Discipline.TRAINING
        # вида нет под рукой — умолчание источника, как обещает SOURCE_DISCIPLINE
        assert discipline_of_record("briefing_entry", None) is Discipline.TRAINING
        # вид есть, но чужой — НЕ умолчание: приписывать нечего
        assert discipline_of_record("briefing_entry", "legacy_free_text") is None
        # источник по таблице — вид не при чём
        assert discipline_of_record("medical_exam", "whatever") is Discipline.MEDICAL
        # событие календаря: вид берётся из extra по SOURCE_KIND_FIELD
        assert SOURCE_KIND_FIELD == {"briefing_entry": "briefing_type"}
        assert (
            discipline_of_event("briefing_entry", {"briefing_type": "fire_repeat"})
            is Discipline.FIRE_SAFETY
        )
        assert discipline_of_event("briefing_entry", {}) is Discipline.TRAINING
        assert discipline_of_event("ppe_issue", {"briefing_type": "fire_repeat"}) is Discipline.PPE


class TestSingleSource:
    """Словарь дисциплин один на продукт — сторож против копии."""

    def test_светофор_клиента_берёт_те_же_дисциплины(self) -> None:
        from app.domains.managed_clients import readiness

        assert readiness.Direction is Discipline
        assert readiness.DIRECTION_TITLES is DISCIPLINE_TITLES
        assert readiness.UNMEASURED_DIRECTIONS is UNMEASURED_DISCIPLINES

    def test_у_каждой_дисциплины_есть_название(self) -> None:
        for code in Discipline:
            assert DISCIPLINE_TITLES[code].strip()

    def test_измеримые_и_неизмеримые_покрывают_все_дисциплины(self) -> None:
        assert set(MEASURED_DISCIPLINES) | set(UNMEASURED_DISCIPLINES) == set(Discipline)
        assert not (set(MEASURED_DISCIPLINES) & set(UNMEASURED_DISCIPLINES))

    def test_у_каждой_неизмеримой_есть_причина(self) -> None:
        for code, reason in UNMEASURED_DISCIPLINES.items():
            assert "не ведётся" in reason, f"{code}: причина должна объяснять отсутствие"


class TestDisciplineOf:
    def test_размеченный_источник_даёт_дисциплину(self) -> None:
        assert discipline_of("medical_exam") is Discipline.MEDICAL
        assert discipline_of("ppe_issue") is Discipline.PPE
        assert discipline_of("briefing_entry") is Discipline.TRAINING

    def test_неклассифицированный_даёт_none(self) -> None:
        assert discipline_of("permit") is None
        assert discipline_of("inspection") is None

    def test_незнакомый_источник_даёт_none(self) -> None:
        assert discipline_of("что-то-новое") is None
