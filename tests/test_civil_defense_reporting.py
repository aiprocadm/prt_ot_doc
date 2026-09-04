"""Контур ГО и ЧС срез-6 (Доп. №1 разд. 56.1): документы и отчётность.

Требование: «Документы и отчётность: приказы, положения, инструкции,
отчётность в органы управления ГОЧС» — ПОСЛЕДНИЙ незакрытый пункт раздела
56.1. **Раздел закрывается целиком.**

СВЕРКА нашла ровно то же, что в разд. 56.2 срез-9 (и это уже приём, а не
совпадение):

1. **Часть пункта закрыта базовым комплектом.** GOCHS_BASE печатает приказ об
   организации ГО, план действий при ЧС, состав комиссии, программу учений и
   журнал занятий — «приказы» из формулировки ТЗ закрыты с первого среза.
2. **Не хватало ТРЁХ вещей: положения, инструкции и самой ОТЧЁТНОСТИ.**
   Положение об объектовом звене РСЧС — документ, которым организация
   определяет своё звено единой системы; инструкции о действиях при ЧС не было
   вовсе; донесение в орган управления не печаталось ничем.
3. **Способ выбран продуктом дважды** — экология (55.3) и БДД (56.2 срез-9)
   закрыли отчётность комплектом форм БЕЗ миграций. Третий раз изобретать
   нечего.

Решения:

* **отдельный комплект, а не дописывание базового**: базовый заводят при
  запуске контура, донесение готовят в день ЧС — смешивать поводы нельзя;
* **обязателен ТОЛЬКО составитель**, и это ОТЛИЧИЕ от отчётности БДД, где
  обязателен ещё и период: положение и инструкция периода не имеют вовсе, а
  донесение готовят и до того, как время события уточнили;
* **незаполненное число пострадавших читается «сведения не внесены», а НЕ
  «ноль»** — здесь это критичнее, чем где-либо в продукте: донесение подают в
  ПЕРВЫЕ ЧАСЫ, когда точных чисел как раз и не знают, и «0 пострадавших» в
  документе, ушедшем в орган управления, — это ложь, за которую отвечает
  подписавший.

ГРАНИЦА: платформа НЕ решает, какое донесение и в какой срок подавать — это
зависит от вида и масштаба ЧС и от требований органа управления ГОЧС. Числа
из реестров (формирования, личный состав, категория объекта) с среза-43 она
ПОДСКАЗЫВАЕТ мастеру, но ответом они не становятся — см.
test_packs_prefill_civil_defense.py; здесь проверяются сами документы.
"""

from __future__ import annotations

import pytest

from app.core.disciplines import Discipline
from app.modules.packs.context import enrich_context
from app.modules.packs.definitions import (
    PACK_CODE_BDD_REPORTS,
    PACK_CODE_CIVIL_DEFENCE,
    PACK_CODE_GOCHS_REPORTS,
    PACK_DEFINITIONS_BY_CODE,
)
from app.modules.packs.fields import questions_for

pytestmark = pytest.mark.anyio

_PACK = PACK_DEFINITIONS_BY_CODE[PACK_CODE_GOCHS_REPORTS]


class TestКомплектОтчётности:
    def test_комплект_размечен_го_и_чс(self) -> None:
        assert _PACK.disciplines == (Discipline.CIVIL_DEFENSE,)

    def test_печатает_положение_инструкцию_и_донесения(self) -> None:
        """Три недостающих вещи из формулировки ТЗ."""

        by_code = {t.code: t for t in _PACK.templates}
        assert by_code["pack_gochs_regulation"].category == "regulation"
        assert by_code["pack_gochs_instruction"].category == "instruction"
        assert by_code["pack_gochs_emergency_report"].category == "report"
        assert by_code["pack_gochs_forces_report"].category == "report"

    def test_базовый_комплект_не_тронут(self) -> None:
        """Сторож: срез добавляет комплект, а не переписывает существующий."""

        base = PACK_DEFINITIONS_BY_CODE[PACK_CODE_CIVIL_DEFENCE]
        assert {t.code for t in base.templates} == {
            "pack_gochs_plan",
            "pack_gochs_order",
            "pack_gochs_commission",
            "pack_gochs_drill",
            "pack_gochs_journal",
        }

    def test_комплекты_не_пересекаются_шаблонами(self) -> None:
        """Один шаблон в двух комплектах — два места правки одного документа."""

        base = {
            t.code for t in PACK_DEFINITIONS_BY_CODE[PACK_CODE_CIVIL_DEFENCE].templates
        }
        assert base & {t.code for t in _PACK.templates} == set()


class TestВопросыМастера:
    def test_обязателен_только_составитель(self) -> None:
        """ОТЛИЧИЕ от отчётности БДД, и оно сознательное.

        Там обязателен ещё и период — потому что отчёт без периода бессмыслен.
        Здесь периода нет у положения и инструкции вовсе, а донесение готовят и
        до того, как время события уточнили. Требовать период значило бы не
        дать открыть мастер в день ЧС.
        """

        required = {f.name for f in questions_for(PACK_CODE_GOCHS_REPORTS) if f.required}
        assert required == {"gochs_report_author"}

        bdd_required = {
            f.name for f in questions_for(PACK_CODE_BDD_REPORTS) if f.required
        }
        assert "bdd_report_period" in bdd_required

    def test_у_каждого_вопроса_есть_подпись(self) -> None:
        for field in questions_for(PACK_CODE_GOCHS_REPORTS):
            assert field.label.strip(), field.name


class TestЧестныеУмолчания:
    def test_невнесённое_число_пострадавших_не_становится_нулём(self) -> None:
        """САМОЕ ВАЖНОЕ В СРЕЗЕ.

        Донесение подают в ПЕРВЫЕ ЧАСЫ, когда точных чисел не знают. Подставь
        ноль — и документ, ушедший в орган управления, ЗАЯВИТ, что
        пострадавших нет. Отвечает за это подписавший.
        """

        context = enrich_context(
            PACK_CODE_GOCHS_REPORTS,
            {"company": {"name": "Тест"}},
            {"gochs_report_author": "Иванов"},
        )
        data = context["data"]
        for key in (
            "gochs_event_injured",
            "gochs_formations_count",
            "gochs_personnel_count",
            "gochs_ppe_coverage",
        ):
            assert data[key] == "сведения не внесены", key
            assert data[key] != "0", key

    def test_неустановленная_категория_названа_словами(self) -> None:
        """Прочерк в категории выглядит как «категории нет», а её не внесли."""

        context = enrich_context(
            PACK_CODE_GOCHS_REPORTS, {"company": {"name": "Тест"}}, {}
        )
        assert context["data"]["facility_category"] == "не установлена"
        assert context["data"]["gochs_responsible"] == "Ответственный не назначен"
        assert context["data"]["gochs_approved_by"] == "не утверждено"

    def test_внесённые_ответы_доходят_до_документа(self) -> None:
        context = enrich_context(
            PACK_CODE_GOCHS_REPORTS,
            {"company": {"name": "Тест"}},
            {
                "gochs_report_author": "Иванов",
                "gochs_event_injured": "3",
                "gochs_event_kind": "разлив топлива",
                "facility_category": "вторая",
            },
        )
        assert context["data"]["gochs_event_injured"] == "3"
        assert context["data"]["gochs_event_kind"] == "разлив топлива"
        assert context["data"]["facility_category"] == "вторая"


class TestГраница:
    def test_платформа_не_обещает_сроки_и_автосбор(self) -> None:
        """ГРАНИЦА-сторож.

        Какое донесение и в какой срок подавать — зависит от вида и масштаба
        ЧС и от требований органа управления. Появись здесь поле «срок подачи»
        или «автозаполнение» — это было бы обещание несуществующего.
        """

        keys = {f.name for f in questions_for(PACK_CODE_GOCHS_REPORTS)}
        assert not any(
            "deadline" in key or "autofill" in key or "auto_" in key for key in keys
        )
