"""Экология срез-8 (Доп. №1 разд. 55.3): отчётность как формы документной фабрики.

Требование: «Экологическая отчётность: 2-ТП (отходы/воздух/водхоз), отчёт по
ПЭК, отчётность по объектам НВОС — как формы документной фабрики» + «декларация
о плате» из пункта о расчёте платы.

СВЕРКА нашла два расхождения:

1. **Отчётных форм экологии не было ВООБЩЕ.** Каталог фабрики держал 12
   сценарных комплектов (приказы, инструктажи, журналы); экология была
   представлена одним ECO_WASTE (реестр, договор, памятка). Ни 2-ТП, ни
   декларации о плате, ни отчёта по ПЭК — притом что данные для них собраны
   срезами 2–7.
2. **Контур packs был разрезан надвое.** Канон ARCH-1 объявил дом контура —
   ``app.modules.packs``, но волна BIZ-50 (09.08.2026) завела fields/readiness/
   scenario_preview в ``app.domains.packs``, и два импорта через границу роняли
   страж ARCH-3 на КАЖДОМ полном прогоне пяти срезов подряд. Починено в этом же
   срезе переносом трёх модулей в канон — allowlist стража не вырос.

Решения:

* **формы — заготовки с плейсхолдерами, как весь каталог**, а не копии
  госформ: платформа даёт документ-основу, а значения специалист берёт из
  реестров экологии (они с этих срезов на экране);
* **суммы и массы в формах — ответы мастера, не вычисления платформы**: у
  строителей контекста нет доступа к БД по построению (чистые функции), и это
  граница, а не ограничение — перенос из журналов без правил округления и
  отчётных периодов госформ был бы подменой смысла;
* **умолчания говорящие и честные**: пустой ответ про превышения читается
  «сведения не внесены», а НЕ «превышений не было» — молчание нельзя выдавать
  за благополучие (тот же довод, что «норматив не внесён» в замерах ПЭК).

ГРАНИЦА: плейсхолдеры всех шести форм живут только в пространствах
``company.*`` / ``site.*`` / ``data.*`` / ``logo`` / ``stamp`` — карточка
клиента и ответы мастера. Никаких «вычисленных платформой» значений в формах
нет.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.packs.context import enrich_context
from app.modules.packs.definitions import (
    PACK_CODE_ECO_REPORTS,
    PACK_DEFINITIONS_BY_CODE,
)
from app.modules.packs.fields import questions_for
from app.services.docx import DocxService


def _pack():
    return PACK_DEFINITIONS_BY_CODE[PACK_CODE_ECO_REPORTS]


_EXPECTED_FORMS = {
    "pack_eco_fee_declaration": "Декларация о плате за НВОС",
    "pack_eco_2tp_waste": "2-ТП (отходы)",
    "pack_eco_2tp_air": "2-ТП (воздух)",
    "pack_eco_2tp_water": "2-ТП (водхоз)",
    "pack_eco_pek_report": "Отчёт по ПЭК",
    "pack_eco_nvos_report": "Отчётность по объектам НВОС",
}


class TestКаталог:
    def test_комплект_отчётности_заведён_и_размечен_экологией(self) -> None:
        pack = _pack()
        assert pack.metadata["discipline"] == "Экология"
        assert [d.value for d in pack.disciplines] == ["ecology"]

    def test_в_комплекте_все_шесть_форм_из_тз(self) -> None:
        """2-ТП три формы + отчёт по ПЭК + отчётность НВОС + декларация о плате."""

        pack = _pack()
        assert {spec.code: spec.name for spec in pack.templates} == _EXPECTED_FORMS

    def test_каждая_форма_помечена_категорией_отчёт(self) -> None:
        """Отчёт — не приказ и не журнал: категория различает их в реестре."""

        for spec in _pack().templates:
            assert spec.category == "report", spec.code

    def test_каждая_форма_собирает_настоящий_docx(self) -> None:
        for spec in _pack().templates:
            payload = spec.builder()
            assert payload[:4] == b"PK\x03\x04", spec.code


class TestВопросыМастера:
    def test_обязательны_отчётный_год_и_составитель(self) -> None:
        """Без года форма бессмысленна, без составителя — безымянна."""

        required = {f.name for f in questions_for(PACK_CODE_ECO_REPORTS) if f.required}
        assert required == {"eco_report_year", "eco_responsible"}

    def test_у_каждого_вопроса_русская_подпись(self) -> None:
        for field in questions_for(PACK_CODE_ECO_REPORTS):
            assert field.label != field.name, field.name
            assert any("а" <= ch <= "я" for ch in field.label.lower()), field.name


class TestКонтекстИГраница:
    def test_плейсхолдеры_только_из_карточки_клиента_и_ответов(self) -> None:
        """ГРАНИЦА: в формах нет значений, «вычисленных платформой».

        Суммы платы и массы 2-ТП — ответы специалиста по данным реестров, а не
        перенос из журналов: у строителей контекста нет доступа к БД по
        построению, и правила округления и отчётные периоды госформ платформе
        неизвестны.
        """

        allowed_prefixes = ("company.", "site.", "data.")
        allowed_flat = {"logo", "stamp"}
        for spec in _pack().templates:
            for placeholder in DocxService.extract_placeholders(spec.builder()):
                ok = placeholder in allowed_flat or placeholder.startswith(
                    allowed_prefixes
                )
                assert ok, f"{spec.code}: неожиданный плейсхолдер {placeholder}"

    def test_умолчание_про_превышения_честное(self) -> None:
        """Пустой ответ = «сведения не внесены», а НЕ «превышений не было»."""

        context = enrich_context(
            PACK_CODE_ECO_REPORTS, {"company": {"name": "Тест"}}, {}
        )
        assert context["data"]["eco_pek_exceedances"] == "сведения не внесены"

    def test_суммы_платы_без_ответа_не_превращаются_в_ноль(self) -> None:
        """«Не внесено» и «ноль рублей» — разные утверждения."""

        context = enrich_context(
            PACK_CODE_ECO_REPORTS, {"company": {"name": "Тест"}}, {}
        )
        for key in ("eco_fee_emissions", "eco_fee_discharges", "eco_fee_waste"):
            assert context["data"][key] == "не внесено", key
            assert context["data"][key] != "0"

    def test_ответ_мастера_доходит_до_контекста(self) -> None:
        context = enrich_context(
            PACK_CODE_ECO_REPORTS,
            {"company": {"name": "Тест"}},
            {"eco_report_year": "2026", "eco_pek_laboratory": "ИЛЦ «Эковоздух»"},
        )
        assert context["data"]["eco_report_year"] == "2026"
        assert context["data"]["eco_pek_laboratory"] == "ИЛЦ «Эковоздух»"


class TestКонсолидацияКонтура:
    def test_каталога_domains_packs_больше_нет(self) -> None:
        """Починка ARCH-3: контур packs снова живёт в одном пакете.

        BIZ-50 создал ``app.domains.packs`` заново поверх канона ARCH-1, и два
        импорта через границу роняли страж на каждом полном прогоне. Модули
        перенесены в ``app.modules.packs``; возвращение каталога уронит и этот
        тест, и страж границ (у packs нет записи в allowlist).
        """

        backend_app = Path(__file__).resolve().parents[1] / "app"
        assert not (backend_app / "domains" / "packs").exists()

    def test_перенесённые_модули_живут_в_каноне(self) -> None:
        import app.modules.packs.fields
        import app.modules.packs.readiness
        import app.modules.packs.scenario_preview

        assert app.modules.packs.fields.__name__ == "app.modules.packs.fields"
        assert app.modules.packs.readiness.__name__ == "app.modules.packs.readiness"
        assert (
            app.modules.packs.scenario_preview.__name__
            == "app.modules.packs.scenario_preview"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
