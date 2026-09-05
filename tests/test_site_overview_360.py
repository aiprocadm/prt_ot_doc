"""BIZ-54-57 срез-3: карточка площадки 360° — правила (Доп. №1 разд. 57.1).

Приёмка §58.3: «Карточка объекта 360° показывает статус по всем применимым
дисциплинам на одном экране».

Здесь — чистые правила без базы. Закрепляется то, что легко потерять правкой:

* светофор площадки красится ТЕМИ ЖЕ правилами, что светофор клиента (иначе
  «жёлтый» на двух соседних экранах означал бы разное);
* наряд-допуск ДОПИСЫВАЕТ расшифровку дисциплины, но НЕ красит её — документ о
  работах не доказывает соответствия;
* признак ОПО — единственная применимость, которая следует из данных площадки;
* виды работ без дисциплины названы словами, а не спрятаны в «прочее».
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.discipline_status import DisciplineCounts, FireSafetyNumbers, TrafficLight
from app.core.disciplines import (
    PERMIT_WORK_TYPE_DISCIPLINE,
    UNMAPPED_PERMIT_WORK_TYPES,
    Discipline,
    discipline_of_permit,
)
from app.domains.sites.overview import (
    NOT_COUNTED,
    OPEN_PERMIT_STATUSES,
    PermitFacts,
    SiteFacts,
    build_site_overview,
)
from app.domains.work_permits.lifecycle import WORK_TYPES
from app.services.discipline_numbers import DisciplineNumbers


def _site(**kwargs):
    base = {
        "id": "site-1",
        "name": "Цех №1",
        "company_id": "company-1",
        "address": "г. Пермь, ул. Заводская, 1",
        "hazard_class": "II",
        "is_hazardous_production_facility": False,
        "opo_register_number": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _numbers(*, medical=None, ppe=None, training_overdue=0) -> DisciplineNumbers:
    return DisciplineNumbers(
        medical=medical or DisciplineCounts(),
        ppe=ppe or DisciplineCounts(),
        training_overdue=training_overdue,
    )


def _row(overview, discipline: Discipline):
    return next(r for r in overview.disciplines if r.discipline is discipline)


class TestРазметкаНарядов:
    """Сверка вскрыла: вид работ — ЗАКРЫТЫЙ список, а не свободная строка."""

    def test_размечены_только_виды_из_закрытого_списка(self) -> None:
        assert set(PERMIT_WORK_TYPE_DISCIPLINE) <= WORK_TYPES

    def test_огневые_это_пожарная_безопасность(self) -> None:
        assert discipline_of_permit("hot_work") is Discipline.FIRE_SAFETY

    def test_газоопасные_это_промышленная_безопасность(self) -> None:
        assert discipline_of_permit("gas_hazardous") is Discipline.INDUSTRIAL_SAFETY

    def test_остальные_виды_не_размечены(self) -> None:
        """Высота, замкнутые пространства, земляные, электро — общая охрана
        труда. Отдельной дисциплины для неё в словаре нет, и приписать наряд к
        медосмотрам ради заполненной клетки значило бы подменить дисциплину."""

        for work_type in ("height", "confined_space", "excavation", "electrical"):
            assert discipline_of_permit(work_type) is None


class TestСветофорПлощадки:
    def test_дисциплины_те_же_и_в_том_же_порядке(self) -> None:
        overview = build_site_overview(_site(), numbers=_numbers(), facts=SiteFacts())
        assert [r.discipline for r in overview.disciplines] == list(Discipline)

    def test_разрыв_красит_красным(self) -> None:
        overview = build_site_overview(
            _site(),
            numbers=_numbers(medical=DisciplineCounts(required=2, missing=1)),
            facts=SiteFacts(),
        )
        assert _row(overview, Discipline.MEDICAL).light is TrafficLight.RED
        assert overview.overall is TrafficLight.RED

    def test_пустая_площадка_не_зелёная(self) -> None:
        """Ни одной измеренной дисциплины — итог not_measured, а не зелёный:
        «норм нет» и «всё в порядке» — разные утверждения."""

        overview = build_site_overview(_site(), numbers=_numbers(), facts=SiteFacts())
        assert overview.overall is TrafficLight.NOT_MEASURED


class TestФактыНеКрасятСветофор:
    """Главный сторож среза: активность ≠ соответствие."""

    def test_наряд_дописывает_расшифровку(self) -> None:
        overview = build_site_overview(
            _site(),
            numbers=_numbers(),
            facts=SiteFacts(
                permits=PermitFacts(total=2, by_discipline={Discipline.FIRE_SAFETY: 2})
            ),
        )
        row = _row(overview, Discipline.FIRE_SAFETY)
        assert "нарядов-допусков: 2" in row.reason
        assert "не ведётся" in row.reason, "прежняя причина обязана остаться"

    def test_наряд_НЕ_красит_дисциплину(self) -> None:
        overview = build_site_overview(
            _site(),
            numbers=_numbers(),
            facts=SiteFacts(
                permits=PermitFacts(total=5, by_discipline={Discipline.FIRE_SAFETY: 5})
            ),
        )
        assert _row(overview, Discipline.FIRE_SAFETY).light is TrafficLight.NOT_MEASURED
        assert overview.overall is TrafficLight.NOT_MEASURED

    def test_дисциплина_без_нарядов_расшифровку_не_меняет(self) -> None:
        clean = build_site_overview(_site(), numbers=_numbers(), facts=SiteFacts())
        withfire = build_site_overview(
            _site(),
            numbers=_numbers(),
            facts=SiteFacts(
                permits=PermitFacts(total=1, by_discipline={Discipline.FIRE_SAFETY: 1})
            ),
        )
        assert _row(clean, Discipline.ECOLOGY).reason == _row(withfire, Discipline.ECOLOGY).reason


class TestСрокиПБПлощадки:
    """Срез-82/83 (разд. 54.1): сроки ПБ площадки и инструктажи её людей — красят, наряды — нет."""

    def test_просрочка_средства_защиты_красит_пб_и_итог(self) -> None:
        overview = build_site_overview(
            _site(),
            numbers=_numbers(),
            facts=SiteFacts(),
            fire_safety=FireSafetyNumbers(units=3, overdue_recharge=1, without_maintenance=2),
        )
        row = _row(overview, Discipline.FIRE_SAFETY)
        assert row.light is TrafficLight.RED
        assert row.reason.startswith("Просрочено по ПБ — перезарядка средств защиты: 1; ")
        assert "средств без записи о работах: 2" in row.reason
        assert overview.overall is TrafficLight.RED, "просрочка объекта входит в итог"

    def test_наряд_дописывается_к_срокам_и_цвет_не_меняет(self) -> None:
        overview = build_site_overview(
            _site(),
            numbers=_numbers(),
            facts=SiteFacts(
                permits=PermitFacts(total=1, by_discipline={Discipline.FIRE_SAFETY: 1})
            ),
            fire_safety=FireSafetyNumbers(units=2, due_soon=1),
        )
        row = _row(overview, Discipline.FIRE_SAFETY)
        assert row.light is TrafficLight.YELLOW
        assert row.reason.endswith("К площадке привязано действующих нарядов-допусков: 1")

    def test_истёкший_инструктаж_человека_площадки_красит_пб_и_итог(self) -> None:
        """Срез-83: поимённый срок ПБ — в цвет площадки, как удостоверение у БДД."""

        overview = build_site_overview(
            _site(),
            numbers=_numbers(),
            facts=SiteFacts(),
            fire_safety=FireSafetyNumbers(overdue_briefings=1, briefings_valid=4),
        )
        row = _row(overview, Discipline.FIRE_SAFETY)
        assert row.light is TrafficLight.RED
        assert row.reason.startswith("Просрочено по ПБ — противопожарные инструктажи: 1; ")
        assert "противопожарных инструктажей действует: 4" in row.reason
        assert overview.overall is TrafficLight.RED

    def test_без_чисел_пб_прежняя_причина(self) -> None:
        overview = build_site_overview(_site(), numbers=_numbers(), facts=SiteFacts())
        row = _row(overview, Discipline.FIRE_SAFETY)
        assert row.light is TrafficLight.NOT_MEASURED
        assert "не ведётся" in row.reason


class TestПрименимостьОПО:
    def test_опо_назван_в_расшифровке_промбеза(self) -> None:
        overview = build_site_overview(
            _site(is_hazardous_production_facility=True, opo_register_number="А12-3456"),
            numbers=_numbers(),
            facts=SiteFacts(),
        )
        row = _row(overview, Discipline.INDUSTRIAL_SAFETY)
        assert "учтена как ОПО" in row.reason
        assert "А12-3456" in row.reason

    def test_опо_без_номера_не_молчит(self) -> None:
        overview = build_site_overview(
            _site(is_hazardous_production_facility=True),
            numbers=_numbers(),
            facts=SiteFacts(),
        )
        assert "без регистрационного номера" in _row(overview, Discipline.INDUSTRIAL_SAFETY).reason

    def test_не_опо_ничего_не_дописывает(self) -> None:
        overview = build_site_overview(_site(), numbers=_numbers(), facts=SiteFacts())
        assert "ОПО" not in _row(overview, Discipline.INDUSTRIAL_SAFETY).reason

    def test_опо_и_наряды_вместе(self) -> None:
        overview = build_site_overview(
            _site(is_hazardous_production_facility=True, opo_register_number="А1"),
            numbers=_numbers(),
            facts=SiteFacts(
                permits=PermitFacts(total=1, by_discipline={Discipline.INDUSTRIAL_SAFETY: 1})
            ),
        )
        row = _row(overview, Discipline.INDUSTRIAL_SAFETY)
        assert "учтена как ОПО" in row.reason and "нарядов-допусков: 1" in row.reason


class TestГраницыНазваныВслух:
    def test_непосчитанное_названо_с_причиной(self) -> None:
        overview = build_site_overview(_site(), numbers=_numbers(), facts=SiteFacts())
        titles = {title for title, _ in overview.not_counted}
        assert titles == {"Проверки", "Инциденты", "Риски"}
        for _title, reason in overview.not_counted:
            assert reason.strip(), "причина обязательна: молчание прочитают как ноль"

    def test_каждая_причина_объясняет_дубли(self) -> None:
        for _title, reason in NOT_COUNTED:
            assert "таблиц" in reason

    def test_действующими_считаются_только_выданные_и_приостановленные(self) -> None:
        assert set(OPEN_PERMIT_STATUSES) == {"issued", "suspended"}

    def test_у_нарядов_без_дисциплины_есть_причина(self) -> None:
        """«Без дисциплины: 1» без объяснения читается как недоделка разметки.

        Сторож против «написано, но никогда не читается»: причина живёт в ядре
        и обязана доезжать до карточки, а не лежать неиспользованной строкой.
        """

        facts = PermitFacts(
            total=1,
            without_discipline=1,
            without_discipline_titles=("работа на высоте",),
            without_discipline_reason=UNMAPPED_PERMIT_WORK_TYPES,
        )
        assert facts.without_discipline_reason == UNMAPPED_PERMIT_WORK_TYPES
        assert "охрана труда" in UNMAPPED_PERMIT_WORK_TYPES
