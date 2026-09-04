"""Применимость дисциплин по выданным модулям (BIZ-54-57 срез-54, приёмка §58.3).

Чистые правила — без базы. Гейт на живых флагах — в
``tests/api/test_site_overview_api.py`` и ``tests/api/test_employee_card_disciplines.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.discipline_status import DisciplineCounts, build_discipline_statuses, worst_light
from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.domains.sites.overview import NOT_COUNTED, SiteFacts, build_site_overview
from app.modules.subscription.registry import SELLABLE_MODULES
from app.services.discipline_applicability import (
    ALL_APPLICABLE,
    DISCIPLINE_MODULE,
    DisciplineApplicability,
    describe_hidden,
    only_applicable,
)
from app.services.discipline_numbers import DisciplineNumbers


def _rows():
    return build_discipline_statuses(
        medical=DisciplineCounts(required=1, missing=1),
        ppe=DisciplineCounts(required=1),
        training_overdue=0,
    )


class TestКартаМодулей:
    def test_каждая_дисциплина_словаря_имеет_решение(self) -> None:
        """Новая дисциплина без строки в карте упала бы KeyError на первой карточке."""

        assert set(DISCIPLINE_MODULE) == set(Discipline)

    def test_коды_модулей_есть_в_реестре(self) -> None:
        """Иначе ``is_module_enabled`` громко упадёт UnknownModuleError на проде."""

        registered = {module.code for module in SELLABLE_MODULES}
        codes = {code for code in DISCIPLINE_MODULE.values() if code is not None}
        assert codes <= registered, codes - registered

    def test_сиз_и_обучение_ядро(self) -> None:
        assert DISCIPLINE_MODULE[Discipline.PPE] is None
        assert DISCIPLINE_MODULE[Discipline.TRAINING] is None


class TestФильтр:
    def test_все_применимы_ничего_не_меняет(self) -> None:
        rows = _rows()
        assert only_applicable(rows, ALL_APPLICABLE) == rows
        assert ALL_APPLICABLE.note is None

    def test_скрытые_убраны_порядок_словаря_сохранён(self) -> None:
        hidden = DisciplineApplicability(hidden=(Discipline.ECOLOGY, Discipline.ROAD_SAFETY))
        rows = only_applicable(_rows(), hidden)
        assert [r.discipline for r in rows] == [
            d for d in Discipline if d not in (Discipline.ECOLOGY, Discipline.ROAD_SAFETY)
        ]

    def test_фраза_называет_скрытое_словами_словаря(self) -> None:
        hidden = DisciplineApplicability(hidden=(Discipline.ECOLOGY, Discipline.CIVIL_DEFENSE))
        assert hidden.note == (
            "Вне редакции арендатора (модуль не выдан или выключен): "
            f"{DISCIPLINE_TITLES[Discipline.ECOLOGY]}, {DISCIPLINE_TITLES[Discipline.CIVIL_DEFENSE]}"
        )

    def test_итог_по_оставшимся(self) -> None:
        """Скрыть красный медосмотр — значит и итог станет по оставшимся; это осознанно."""

        rows = only_applicable(_rows(), DisciplineApplicability(hidden=(Discipline.MEDICAL,)))
        assert worst_light(rows).value == "green"


class TestКарточкаПлощадки:
    @staticmethod
    def _site() -> SimpleNamespace:
        return SimpleNamespace(
            id="s1",
            name="Цех",
            company_id="c",
            address=None,
            hazard_class=None,
            is_hazardous_production_facility=False,
            opo_register_number=None,
        )

    def test_скрытое_названо_в_не_посчитано(self) -> None:
        overview = build_site_overview(
            self._site(),
            numbers=DisciplineNumbers(
                medical=DisciplineCounts(required=1, missing=1),
                ppe=DisciplineCounts(),
                training_overdue=0,
            ),
            facts=SiteFacts(),
            applicability=DisciplineApplicability(hidden=(Discipline.ECOLOGY,)),
        )
        assert Discipline.ECOLOGY not in {r.discipline for r in overview.disciplines}
        assert len(overview.disciplines) == len(Discipline) - 1
        assert overview.not_counted[: len(NOT_COUNTED)] == NOT_COUNTED
        title, reason = overview.not_counted[-1]
        assert title == "Дисциплины вне редакции"
        assert reason.startswith("Экология — модуль не выдан арендатору или выключен")

    def test_без_скрытого_список_прежний(self) -> None:
        overview = build_site_overview(
            self._site(),
            numbers=DisciplineNumbers(
                medical=DisciplineCounts(), ppe=DisciplineCounts(), training_overdue=0
            ),
            facts=SiteFacts(),
        )
        assert overview.not_counted == NOT_COUNTED


class TestФразаДляСводокФактов:
    """Срез-56: центр внимания и разрез считают факты, и факт редакция не прячет."""

    def test_скрытые_пустые_вне_редакции_скрытые_с_фактами_названы_отдельно(self) -> None:
        hidden = DisciplineApplicability(
            hidden=(Discipline.ECOLOGY, Discipline.CIVIL_DEFENSE, Discipline.ROAD_SAFETY)
        )
        phrase = describe_hidden(hidden, with_facts=[Discipline.ROAD_SAFETY])
        assert phrase == (
            "Вне редакции арендатора (модуль не выдан или выключен): Экология, ГО и ЧС; "
            "БДД — модуль не выдан или выключен, но открытые записи есть и показаны как факты"
        )

    def test_только_с_фактами_без_части_вне_редакции(self) -> None:
        hidden = DisciplineApplicability(hidden=(Discipline.MEDICAL,))
        assert describe_hidden(hidden, with_facts=[Discipline.MEDICAL]) == (
            "Медосмотры — модуль не выдан или выключен, но открытые записи есть "
            "и показаны как факты"
        )

    def test_факты_по_применимой_дисциплине_во_фразу_не_попадают(self) -> None:
        hidden = DisciplineApplicability(hidden=(Discipline.ECOLOGY,))
        assert describe_hidden(hidden, with_facts=[Discipline.MEDICAL]) == hidden.note

    def test_без_скрытого_фразы_нет(self) -> None:
        assert describe_hidden(ALL_APPLICABLE, with_facts=[Discipline.MEDICAL]) is None
