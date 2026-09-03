"""BIZ-54-57 срез-5: сценарные комплекты размечены дисциплинами (§58.3).

Приёмка §58.3, последний пункт: «Для каждой дисциплины есть библиотека
предустановленных правил (starter-pack) и **минимум один готовый сценарный
комплект** (разд. 50)».

**Что нашла сверка.** Комплекты по дисциплинам в каталоге были — ПБ, ПромБез,
экология, ГО-ЧС. Но дисциплина хранилась ТОЛЬКО свободной строкой в
``metadata``: «Охрана труда и промышленная безопасность», «Любая — по типу
надзора», «Общее руководство». Со словарём дисциплин продукта такие строки не
сходятся, поэтому требование приёмки нельзя было ни проверить, ни заметить
пропажу. И пропажа была: **у БДД комплекта не существовало вовсе** — в таблице
разд. 50.1 этой строки нет, а приёмка требует комплект для КАЖДОЙ дисциплины.

Здесь закреплено то, что теперь проверяемо машинно.
"""

from __future__ import annotations

import pytest

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.modules.packs.definitions import (
    DEFAULT_PACKS,
    PACK_CODE_BDD_REPORTS,
    PACK_CODE_ROAD_SAFETY,
    PACK_DEFINITIONS_BY_CODE,
    PACKS_WITHOUT_DISCIPLINE,
    discipline_pack_coverage,
    packs_for,
)


class TestПокрытиеДисциплин:
    """Главный сторож среза: строка приёмки стала проверкой, а не словами."""

    @pytest.mark.parametrize("discipline", list(Discipline), ids=lambda d: d.value)
    def test_у_каждой_дисциплины_есть_комплект(self, discipline: Discipline) -> None:
        assert packs_for(discipline), DISCIPLINE_TITLES[discipline]

    def test_покрытие_перечисляет_все_дисциплины_тз(self) -> None:
        rows = discipline_pack_coverage()
        assert {row["discipline"] for row in rows} == {d.value for d in Discipline}

    def test_бдд_закрыта_собственными_комплектами(self) -> None:
        """Единственная дисциплина, у которой комплекта не было вовсе.

        ПРОВЕРКА ОСЛАБЛЕНА СОЗНАТЕЛЬНО (разд. 56.2 срез-9). Раньше здесь
        стояло РАВЕНСТВО одному комплекту — верное, пока у БДД был только
        базовый. Срез-9 добавил отчётность (положение о системе управления,
        отчёты об аварийности и мероприятиях, приказ о закреплении ТС), и
        равенство стало ложным ПО СУЩЕСТВУ: требовать его значило бы запретить
        дисциплине второй комплект, чего приёмка §58.3 не требует и не
        подразумевает.

        Что осталось под сторожем и стало важнее: БАЗОВЫЙ комплект никуда не
        делся (иначе дисциплина осталась бы без сценарного), и оба комплекта
        размечены именно БДД.
        """

        packs = packs_for(Discipline.ROAD_SAFETY)
        codes = {pack.code for pack in packs}
        assert PACK_CODE_ROAD_SAFETY in codes
        assert PACK_CODE_BDD_REPORTS in codes
        assert PACK_DEFINITIONS_BY_CODE[PACK_CODE_ROAD_SAFETY] in packs

    def test_отчётность_бдд_печатает_положение_и_отчёты(self) -> None:
        """ТЗ просит «отчётность и документы (приказы, положения, планы)».

        Приказ, инструкция и план печатались базовым комплектом с первого
        среза. Не хватало ОТЧЁТНОСТИ и ПОЛОЖЕНИЯ — а положение о системе
        управления БДД это документ, с которого проверка начинается.
        """

        pack = PACK_DEFINITIONS_BY_CODE[PACK_CODE_BDD_REPORTS]
        categories = {template.category for template in pack.templates}
        assert "report" in categories
        assert "regulation" in categories
        codes = {template.code for template in pack.templates}
        assert "pack_bdd_regulation" in codes


class TestРазметкаЧестная:
    def test_пустая_разметка_только_с_причиной(self) -> None:
        """Пустая разметка и ЗАБЫТАЯ разметка выглядят одинаково.

        Без этой проверки новый комплект без дисциплины молча уехал бы в
        каталог, и «у каждой дисциплины есть комплект» осталось бы верным
        только на бумаге.
        """

        for pack in DEFAULT_PACKS:
            if pack.disciplines:
                continue
            assert pack.code in PACKS_WITHOUT_DISCIPLINE, pack.code
            assert PACKS_WITHOUT_DISCIPLINE[pack.code].strip(), pack.code

    def test_причина_не_протухла(self) -> None:
        """Обратная половина: появилась разметка — причина обязана уйти."""

        for code in PACKS_WITHOUT_DISCIPLINE:
            pack = PACK_DEFINITIONS_BY_CODE[code]
            assert not pack.disciplines, code

    def test_коды_дисциплин_из_общего_словаря(self) -> None:
        """Своего перечисления у комплектов быть не должно — оно бы разошлось."""

        for pack in DEFAULT_PACKS:
            for discipline in pack.disciplines:
                assert isinstance(discipline, Discipline), pack.code

    def test_человеческая_подпись_осталась(self) -> None:
        """Строка в metadata — подпись для человека; коды её не заменяют."""

        for pack in DEFAULT_PACKS:
            assert pack.metadata.get("discipline", "").strip(), pack.code


class TestКомплектБДД:
    def test_состав_комплекта(self) -> None:
        pack = PACK_DEFINITIONS_BY_CODE[PACK_CODE_ROAD_SAFETY]
        assert [spec.code for spec in pack.templates] == [
            "pack_bdd_order",
            "pack_bdd_instruction",
            "pack_bdd_action_plan",
            "pack_bdd_briefing",
        ]

    def test_порядок_совпадает_с_составом(self) -> None:
        """Расхождение дало бы комплект, где документ есть, а в ZIP его нет."""

        for pack in DEFAULT_PACKS:
            assert set(pack.item_order) == {spec.code for spec in pack.templates}, pack.code
            assert len(pack.item_order) == len(pack.templates), pack.code

    def test_коды_шаблонов_уникальны_по_каталогу(self) -> None:
        seen: dict[str, str] = {}
        for pack in DEFAULT_PACKS:
            for spec in pack.templates:
                assert spec.code not in seen, f"{spec.code}: {seen.get(spec.code)} и {pack.code}"
                seen[spec.code] = pack.code
