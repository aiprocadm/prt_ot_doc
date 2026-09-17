"""Контур БДД срез-9 (Доп. №1 разд. 56.2): отчётность и документы.

Требование: «Отчётность по БДД и документы (приказы, положения, планы
мероприятий)» — ПОСЛЕДНИЙ пункт раздела 56.2. **Раздел закрывается целиком.**

СВЕРКА нашла:

1. **Половина пункта закрыта с первого среза.** Базовый комплект BDD_BASE
   печатает приказ об ответственном, инструкцию и план мероприятий — то есть
   «приказы» и «планы мероприятий» из формулировки ТЗ. Строить их заново было
   бы дублем.
2. **Не хватало ДВУХ вещей: отчётности и ПОЛОЖЕНИЯ.** Положение о системе
   управления БДД — документ, с которого начинается проверка организации,
   эксплуатирующей транспорт, и в комплекте его не было вовсе.
3. **Способ уже выбран продуктом, изобретать не пришлось.** Экология закрыла
   свою отчётность (разд. 55.3) комплектом форм категории ``report`` БЕЗ
   миграций — комплекты материализуются лениво. Тот же приём здесь.

Решения:

* **отдельный комплект, а не дописывание базового**: базовый заводят при
  запуске контура, отчётность собирают в конце периода — это разные поводы
  открыть мастер, и смешивать их значило бы каждый раз показывать половину
  ненужных вопросов;
* **обязательны ТОЛЬКО период и составитель**: без периода отчёт бессмыслен,
  без составителя безымянен; остальное вносится по мере готовности;
* **незаполненное число читается «сведения не внесены», а НЕ «ноль»** — и
  здесь это важнее, чем где-либо: подставь ноль, и отчёт о состоянии
  аварийности ЗАЯВИТ, что происшествий не было, хотя их просто не внесли.
  Молчание нельзя выдавать за благополучие.

ГРАНИЦА: **числа в отчёт подставляет специалист, а не платформа.** Сводка
контура их показывает, но собирать документ из реестров платформа пока не
умеет НИ ДЛЯ ОДНОЙ дисциплины (то же у отчётных форм экологии).
Предзаполнение мастера из реестров — отдельная работа, названная в журнале
волн. Заявлять здесь автосбор значило бы обещать несуществующее.
"""

from __future__ import annotations

import pytest

from app.core.disciplines import Discipline
from app.modules.packs.context import enrich_context
from app.modules.packs.definitions import (
    PACK_CODE_BDD_REPORTS,
    PACK_CODE_ROAD_SAFETY,
    PACK_DEFINITIONS_BY_CODE,
)
from app.modules.packs.fields import questions_for

pytestmark = pytest.mark.anyio

_PACK = PACK_DEFINITIONS_BY_CODE[PACK_CODE_BDD_REPORTS]


class TestКомплектОтчётности:
    def test_комплект_размечен_бдд(self) -> None:
        assert _PACK.disciplines == (Discipline.ROAD_SAFETY,)

    def test_печатает_положение_отчёты_и_приказ(self) -> None:
        """ТЗ просит «приказы, положения, планы мероприятий» и отчётность."""

        by_code = {t.code: t for t in _PACK.templates}
        assert by_code["pack_bdd_regulation"].category == "regulation"
        assert by_code["pack_bdd_accident_report"].category == "report"
        assert by_code["pack_bdd_measures_report"].category == "report"
        assert by_code["pack_bdd_assignment_order"].category == "order"

    def test_базовый_комплект_не_тронут(self) -> None:
        """Сторож: срез добавляет комплект, а не переписывает существующий.

        Приказ, инструкция и план мероприятий печатались BDD_BASE с первого
        среза — перенеси их сюда, и запуск контура остался бы без документов.
        """

        base = PACK_DEFINITIONS_BY_CODE[PACK_CODE_ROAD_SAFETY]
        base_codes = {t.code for t in base.templates}
        assert base_codes == {
            "pack_bdd_order",
            "pack_bdd_instruction",
            "pack_bdd_action_plan",
            "pack_bdd_briefing",
        }

    def test_комплекты_не_пересекаются_шаблонами(self) -> None:
        """Один шаблон в двух комплектах — два места правки одного документа."""

        base = {t.code for t in PACK_DEFINITIONS_BY_CODE[PACK_CODE_ROAD_SAFETY].templates}
        reports = {t.code for t in _PACK.templates}
        assert base & reports == set()


class TestВопросыМастера:
    def test_обязательны_только_период_и_составитель(self) -> None:
        """Без периода отчёт бессмыслен, без составителя безымянен.

        Сделай обязательными числа — и специалист не сможет открыть мастер,
        пока не соберёт всё; а собирают их по частям.
        """

        fields = questions_for(PACK_CODE_BDD_REPORTS)
        required = {f.name for f in fields if f.required}
        assert required == {"bdd_report_period", "bdd_report_author"}

    def test_у_каждого_вопроса_есть_подпись(self) -> None:
        """Без подписи вопрос уедет в мастер сырым ключом."""

        for field in questions_for(PACK_CODE_BDD_REPORTS):
            assert field.label.strip(), field.name


class TestЧестныеУмолчания:
    def test_невнесённое_число_дтп_не_становится_нулём(self) -> None:
        """САМОЕ ВАЖНОЕ В СРЕЗЕ.

        Подставь ноль — и отчёт о состоянии аварийности ЗАЯВИТ, что
        происшествий не было, хотя их просто не внесли. Молчание нельзя
        выдавать за благополучие: подписывать такой отчёт человек будет своей
        фамилией.
        """

        context = enrich_context(
            PACK_CODE_BDD_REPORTS,
            {"company": {"name": "Тест"}},
            {"bdd_report_period": "2026 год", "bdd_report_author": "Иванов"},
        )
        data = context["data"]
        for key in (
            "bdd_report_accidents",
            "bdd_report_injured",
            "bdd_report_violations",
            "bdd_report_vehicles",
            "bdd_report_drivers",
            "bdd_measures_planned",
            "bdd_measures_done",
        ):
            assert data[key] == "сведения не внесены", key
            assert data[key] != "0", key

    def test_внесённые_ответы_доходят_до_документа(self) -> None:
        context = enrich_context(
            PACK_CODE_BDD_REPORTS,
            {"company": {"name": "Тест"}},
            {
                "bdd_report_period": "2026 год",
                "bdd_report_author": "Иванов",
                "bdd_report_accidents": "2",
                "bdd_report_violations": "17",
            },
        )
        assert context["data"]["bdd_report_period"] == "2026 год"
        assert context["data"]["bdd_report_accidents"] == "2"
        assert context["data"]["bdd_report_violations"] == "17"

    def test_неназначенный_ответственный_назван_словами(self) -> None:
        """Документ с прочерком выглядит оформленным, хотя ответственного нет."""

        context = enrich_context(PACK_CODE_BDD_REPORTS, {"company": {"name": "Тест"}}, {})
        assert context["data"]["bdd_responsible"] == "Ответственный не назначен"
        assert context["data"]["bdd_approved_by"] == "не утверждено"


class TestГраница:
    def test_платформа_не_обещает_автосбор_чисел(self) -> None:
        """ГРАНИЦА-сторож: числа вносит специалист, а не платформа.

        Сводка контура их показывает, но собирать документ из реестров
        платформа пока не умеет ни для одной дисциплины. Появись здесь поле
        вроде ``bdd_report_autofill`` — это было бы обещание несуществующего.
        """

        keys = {f.name for f in questions_for(PACK_CODE_BDD_REPORTS)}
        assert not any("autofill" in key or "auto_" in key or "computed" in key for key in keys)
