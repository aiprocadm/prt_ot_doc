"""BIZ-50 срез-2 — каталог сценариев (Доп. №1, разд. 50.1). Без БД.

ТЗ называет восемь сценариев «минимальным набором для запуска». Половина
минимального набора — это не половина пользы: аутсорсер, не нашедший в
каталоге «приём нового сотрудника», собирает комплект руками, и весь мастер
для него не существует.

Поэтому здесь закреплено ИМЕННО соответствие строкам ТЗ, а не число пакетов:
счётчик «пакетов >= 8» прошёл бы и на восьми копиях одного сценария.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.modules.packs.definitions import (
    DEFAULT_PACKS,
    PACK_CODE_CIVIL_DEFENCE,
    PACK_CODE_CONTRACTOR,
    PACK_CODE_FIRE_INSPECTION,
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_NEW_EMPLOYEE,
    PACK_CODE_SITE_ACCESS,
    PACK_CODE_WASTE,
    PACK_DEFINITIONS_BY_CODE,
)

#: Строка таблицы разд. 50.1 → код пакета в каталоге.
TZ_SCENARIOS = {
    "Выход на объект / допуск бригады": PACK_CODE_SITE_ACCESS,
    "Несчастный случай": PACK_CODE_INCIDENT,
    "Подготовка к проверке": PACK_CODE_INSPECTION_PREP,
    "Новый подрядчик": PACK_CODE_CONTRACTOR,
    "Приём нового сотрудника": PACK_CODE_NEW_EMPLOYEE,
    "Пожарная проверка объекта": PACK_CODE_FIRE_INSPECTION,
    "Экологический пакет": PACK_CODE_WASTE,
    "Пакет ГО и ЧС": PACK_CODE_CIVIL_DEFENCE,
}


@pytest.mark.parametrize(("requirement", "code"), sorted(TZ_SCENARIOS.items()))
def test_every_tz_scenario_has_a_pack(requirement: str, code: str) -> None:
    assert code in PACK_DEFINITIONS_BY_CODE, f"разд. 50.1 «{requirement}» нечем закрыть"


def test_pack_codes_are_unique() -> None:
    """Код пакета — естественный ключ: дубль молча перезаписал бы чужой пакет."""

    duplicates = [
        code for code, count in Counter(p.code for p in DEFAULT_PACKS).items() if count > 1
    ]
    assert duplicates == []


def test_template_codes_are_unique_across_the_catalog() -> None:
    """Шаблоны сеются по коду в ОДИН арендаторский каталог.

    Совпадение кодов у двух сценариев означало бы, что второй пакет молча
    получает документ первого — и это заметили бы уже по сгенерированному
    комплекту у клиента.
    """

    codes = [spec.code for pack in DEFAULT_PACKS for spec in pack.templates]
    duplicates = [code for code, count in Counter(codes).items() if count > 1]
    assert duplicates == []


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_item_order_matches_templates(pack) -> None:
    """Порядок документов обязан перечислять ровно то, что есть в пакете.

    Лишний код в порядке — документ, которого нет; пропущенный — документ,
    который не попадёт в комплект. И то и другое видно только на выдаче.
    """

    assert sorted(pack.item_order) == sorted(spec.code for spec in pack.templates)


@pytest.mark.parametrize("pack", DEFAULT_PACKS, ids=lambda pack: pack.code)
def test_every_template_builds_a_docx(pack) -> None:
    for spec in pack.templates:
        payload = spec.builder()
        assert isinstance(payload, bytes) and payload
        # PK\x03\x04 — сигнатура zip, то есть настоящего .docx, а не пустышки.
        assert payload[:4] == b"PK\x03\x04", f"{spec.code} не собрался в docx"


def test_every_pack_declares_its_discipline() -> None:
    """Дисциплина — колонка таблицы разд. 50.1, по ней и ищут сценарий.

    Поле ``module`` хранит грубую группу для БД (ot/fire_safety/health/custom)
    и не умеет сказать «Гражданская оборона и ЧС»; добавлять значение в тип
    БД ради ярлыка значило бы миграцию.
    """

    missing = [pack.code for pack in DEFAULT_PACKS if not pack.metadata.get("discipline")]
    assert missing == []
