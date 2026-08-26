"""BIZ-50 срез-4 — объявленные поля сценария сверены с поведением. Без БД.

Список полей объявлен отдельно от строителя контекста, значит два описания
одного и того же могут разъехаться. Проверять их сравнением текста нельзя:
часть полей строитель читает в цикле, и статический разбор их не видит —
именно так и появляются «проверки», которые ничего не проверяют.

Поэтому оба теста ПОВЕДЕНЧЕСКИЕ: подставляем метку и смотрим, дошла ли она до
контекста, из которого печатается документ.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.packs.context import enrich_context
from app.modules.packs.definitions import DEFAULT_PACKS
from app.modules.packs.fields import (
    BRANDING_FIELDS,
    SCENARIO_FIELDS,
    expand_answers,
    questions_for,
)
from app.services.docx import DocxService

_MARK = "СТРАЖ-9137"

#: Пространства, которые заполняет конвейер из карточки клиента, а не
#: специалист. Их мастер не спрашивает — в этом и смысл второго шага.
_ENTITY_PREFIXES = ("company.", "site.", "person.")


def _pipeline_context() -> dict[str, Any]:
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


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(item) for item in value)
    return str(value)


def _placeholders(pack) -> set[str]:
    used: set[str] = set()
    for spec in pack.templates:
        used |= DocxService.extract_placeholders(spec.builder())
    return used


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_every_scenario_declares_its_questions(pack) -> None:
    assert questions_for(pack.code), f"{pack.code}: мастеру нечего спросить — сценарий не объявлен"


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_declared_field_actually_reaches_the_document(pack) -> None:
    """Объявленное поле обязано доходить до документа.

    Поле-призрак (опечатка в имени, переименование в строителе) выглядит в
    мастере как обычный вопрос: специалист отвечает, а ответ никуда не идёт.
    """

    for field in questions_for(pack.code):
        answers = expand_answers({field.name: _MARK})
        context = enrich_context(pack.code, _pipeline_context(), answers)
        assert _MARK in _flatten(
            context
        ), f"{pack.code}: ответ на «{field.label}» никуда не попадает"


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_no_user_field_is_left_undeclared(pack) -> None:
    """Ни одно заполняемое место документа не должно остаться без вопроса.

    Забытое поле = графа, которую невозможно заполнить через мастер: она
    навсегда останется прочерком, и заметят это по документу у клиента.
    """

    answers = expand_answers({field.name: _MARK for field in questions_for(pack.code)})
    context = enrich_context(pack.code, _pipeline_context(), answers)

    unreachable = []
    for name in sorted(_placeholders(pack)):
        if name.startswith(_ENTITY_PREFIXES) or name in BRANDING_FIELDS:
            continue
        node: Any = context
        for part in name.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if _MARK not in _flatten(node):
            unreachable.append(name)
    assert unreachable == [], f"{pack.code}: нечем заполнить {unreachable}"


def test_labels_are_unique_per_scenario() -> None:
    """Два вопроса с одинаковой подписью — это форма, в которой нельзя ответить."""

    for code, fields in SCENARIO_FIELDS.items():
        labels = [field.label for field in fields]
        assert len(labels) == len(set(labels)), f"{code}: повторяющиеся подписи вопросов"


def test_client_facts_are_never_asked() -> None:
    """Организацию, объект и сотрудника платформа уже знает (BIZ-49).

    Спрашивать их второй раз и есть та «долгая настройка клиента», от которой
    уходит разд. 50.2.
    """

    forbidden = {"company", "company_name", "inn", "site", "site_address", "person"}
    for code, fields in SCENARIO_FIELDS.items():
        # «person» в сценарии выхода на объект — это ФИО инструктируемого из
        # состава бригады, а не карточка сотрудника; исключение осознанное.
        names = {field.name for field in fields} - {"person"}
        assert not (names & forbidden), f"{code}: мастер спрашивает то, что уже известно"


#: Потолок обязательных вопросов на сценарий. Ограничение по АБСОЛЮТНОМУ
#: числу, а не по доле: у «несчастного случая» мало необязательных полей, но
#: акт без места и обстоятельств бесполезен — доля там законно велика. Опасна
#: не доля, а длина обязательной части: форму на дюжину обязательных полей
#: не заполняют, её обходят.
_MAX_REQUIRED = 6


def test_required_core_stays_short() -> None:
    """Обязательным должно быть то, без чего документ бессмыслен."""

    for code, fields in SCENARIO_FIELDS.items():
        required = [field for field in fields if field.required]
        assert required, f"{code}: не объявлено ни одного обязательного поля"
        assert len(required) <= _MAX_REQUIRED, (
            f"{code}: обязательных вопросов {len(required)} — мастер превращается в "
            "пустую форму, которую обходят"
        )
        assert len(required) < len(fields), f"{code}: обязательно всё — это не мастер, а анкета"
