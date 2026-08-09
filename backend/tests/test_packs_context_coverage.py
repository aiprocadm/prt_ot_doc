"""BIZ-50 срез-3 — у каждого плейсхолдера комплекта есть значение. Без БД.

Сверка перед этим срезом вскрыла целый класс дефектов, невидимый обычными
тестами: шаблон просит ``{{ person.full_name }}``, а конвейер кладёт в контекст
``first_name``/``last_name`` — графа «Работник:» выходит ПУСТОЙ. Документ при
этом генерируется, скачивается и подшивается как заполненный.

Так было в четырёх сценариях, добавленных срезом-2 (у них вообще не было
строителя контекста: ни логотипа, ни печати, ни одного значения), и в
«Выходе на объект» — ПЕРВОМ пакете каталога: пустыми выходили должность,
название журнала, дата, инструктирующий и перечень выданных СИЗ.

Этот тест — страж класса, а не отдельных полей: он сам достаёт плейсхолдеры
из собранных шаблонов и требует значение каждому. Новый пакет без строителя
контекста теперь не пройдёт.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.packs.context import enrich_context
from app.modules.packs.definitions import DEFAULT_PACKS
from app.services.docx import DocxService


def _pipeline_context() -> dict[str, Any]:
    """Контекст в том виде, в каком его собирает конвейер генерации.

    Повторяет ``app.api.routes.packs._common`` — если тест возьмёт форму
    побогаче, он будет проверять сам себя, а не рабочий путь.
    """

    return {
        "company": {
            "id": "c-1",
            "name": "ООО Ромашка",
            "tax_id": "7700000000",
            "address": "г. Москва, ул. Ленина, 1",
            "inn": "7700000000",
        },
        "site": {"id": "s-1", "name": "Склад", "address": "г. Москва, ул. Ленина, 1"},
        "data": {},
    }


def _resolve(context: dict[str, Any], path: str) -> Any:
    node: Any = context
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_every_placeholder_gets_a_value(pack) -> None:
    """Пустая графа в готовом документе хуже отсутствия документа.

    Отсутствие видно сразу, пустая графа — только тому, кто будет по этому
    документу отвечать.
    """

    used: set[str] = set()
    for spec in pack.templates:
        used |= DocxService.extract_placeholders(spec.builder())
    assert used, f"{pack.code}: шаблоны без единого плейсхолдера — проверять нечего"

    # Специалист ничего не дозаполнил: худший реальный случай.
    context = enrich_context(pack.code, _pipeline_context(), {})
    missing = sorted(name for name in used if _resolve(context, name) is None)
    assert missing == [], f"{pack.code}: без значения останутся {missing}"


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_empty_values_become_a_dash_not_a_blank(pack) -> None:
    """Прочерк читается как «не заполнено», пустая строка — как брак печати."""

    used: set[str] = set()
    for spec in pack.templates:
        used |= DocxService.extract_placeholders(spec.builder())
    context = enrich_context(pack.code, _pipeline_context(), {})

    blanks = []
    for name in sorted(used):
        value = _resolve(context, name)
        if isinstance(value, str) and not value.strip():
            blanks.append(name)
    assert blanks == [], f"{pack.code}: пустые строки вместо прочерка — {blanks}"


def test_user_data_is_not_overwritten_by_defaults() -> None:
    """Умолчание не должно затирать то, что специалист ввёл руками."""

    from app.modules.packs.definitions import PACK_CODE_NEW_EMPLOYEE

    context = enrich_context(
        PACK_CODE_NEW_EMPLOYEE,
        _pipeline_context(),
        {"employee_name": "Иванов Иван Иванович", "position": "Слесарь"},
    )
    assert context["data"]["employee_name"] == "Иванов Иван Иванович"
    assert context["data"]["position"] == "Слесарь"


def test_person_full_name_is_composed_from_parts() -> None:
    """Конвейер кладёт части имени, шаблон просит целое."""

    from app.modules.packs.definitions import PACK_CODE_SITE_ACCESS

    base = _pipeline_context()
    base["person"] = {"first_name": "Иван", "last_name": "Иванов", "middle_name": "Иванович"}
    context = enrich_context(PACK_CODE_SITE_ACCESS, base, {})
    assert context["person"]["full_name"] == "Иванов Иван Иванович"


def test_contractor_readiness_defaults_to_not_confirmed() -> None:
    """Незаполненная проверка готовности — это НЕ пройденная проверка."""

    from app.modules.packs.definitions import PACK_CODE_CONTRACTOR

    context = enrich_context(PACK_CODE_CONTRACTOR, _pipeline_context(), {})
    payload = context["data"]
    assert payload["training_status"] == "не подтверждено"
    assert payload["medical_status"] == "не подтверждено"
    assert payload["insurance_status"] == "не подтверждено"
