"""Обновление эталонного набора (BIZ-52 срез-17, Доп. №1 разд. 52.3)."""

from __future__ import annotations

import json

from app.domains.reseller.pack_updates import (
    DEFAULT_REVISION,
    plan_pack_update,
    revision_of,
)
from app.services.tenants.bootstrap.service import STARTER_PACK_ROOT


def _pack(revision: int, **reference) -> dict:
    return {
        "version": "v1",
        "pack": "default",
        "revision": revision,
        "reference_data": reference,
    }


def test_новые_строки_эталона_предлагаются():
    update = plan_pack_update(
        applied=_pack(1, hazards=["Пожар"]),
        current=_pack(2, hazards=["Пожар", "Электротравма"]),
    )

    assert update.additions == {"hazards": ["Электротравма"]}
    assert update.has_updates is True


def test_удалённое_клиентом_не_воскресает():
    """Главное свойство «без затирания правок».

    Строка была в применённой редакции — значит клиент её видел и мог удалить
    осознанно. Сравнивай мы с состоянием справочников, каждое обновление
    возвращало бы удалённое, и человек перестал бы нажимать кнопку.
    """

    update = plan_pack_update(
        applied=_pack(1, hazards=["Пожар", "Электротравма"]),
        current=_pack(2, hazards=["Пожар", "Электротравма"]),
    )

    assert update.has_updates is False


def test_удаление_строки_из_эталона_не_удаляет_у_клиента():
    # Клиент мог построить на ней работу; «обновление набора» не то действие,
    # после которого данные исчезают.
    update = plan_pack_update(
        applied=_pack(1, hazards=["Пожар", "Электротравма"]),
        current=_pack(2, hazards=["Пожар"]),
    )

    assert update.additions == {}
    assert update.has_updates is False


def test_совпадение_без_учёта_регистра():
    update = plan_pack_update(
        applied=_pack(1, hazards=["Пожар"]), current=_pack(2, hazards=["ПОЖАР"])
    )

    assert update.has_updates is False


def test_без_слепка_предлагается_весь_набор():
    update = plan_pack_update(applied=None, current=_pack(3, hazards=["Пожар"]))

    assert update.applied_unknown is True
    assert update.additions == {"hazards": ["Пожар"]}


def test_разные_сообщения_для_разных_случаев():
    # «Обновлений нет» и «сравнивать не с чем» — разные вещи: во втором случае
    # человек должен понимать, что предложен весь набор, а не разница.
    no_updates = plan_pack_update(
        applied=_pack(2, hazards=["Пожар"]), current=_pack(2, hazards=["Пожар"])
    )
    unknown = plan_pack_update(applied=None, current=_pack(2, hazards=["Пожар"]))

    assert "Обновлений нет" in no_updates.summary
    assert "неизвестна" in unknown.summary


def test_сводка_называет_редакции_и_количество():
    update = plan_pack_update(
        applied=_pack(1, hazards=["Пожар"]),
        current=_pack(4, hazards=["Пожар", "Шум", "Вибрация"]),
    )

    assert "1 → 4" in update.summary
    assert "2" in update.summary


def test_редакция_по_умолчанию_первая():
    # Иначе добавление поля объявило бы все существующие наборы обновлёнными.
    assert revision_of({"pack": "default"}) == DEFAULT_REVISION
    assert revision_of(None) == DEFAULT_REVISION
    assert revision_of({"revision": "мусор"}) == DEFAULT_REVISION
    assert revision_of({"revision": 0}) == DEFAULT_REVISION


def test_неприменимые_виды_в_обновление_не_попадают():
    # Виды-перечисления не ложатся в таблицы; предлагать их «обновлением»
    # значило бы обещать то, чего не произойдёт.
    update = plan_pack_update(
        applied=_pack(1),
        current=_pack(2, briefing_types=["Вводный"], hazards=["Пожар"]),
    )

    assert update.additions == {"hazards": ["Пожар"]}


def test_у_всех_эталонов_репозитория_есть_редакция():
    """Страж: набор без редакции сравнивать не с чем."""

    for path in sorted((STARTER_PACK_ROOT / "v1").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert revision_of(payload) >= 1, path.name


def test_обновление_эталона_репозитория_видно_как_добавление():
    """Проба на настоящем файле, а не на выдуманном словаре."""

    current = json.loads(
        (STARTER_PACK_ROOT / "v1" / "construction.json").read_text(encoding="utf-8")
    )
    applied = json.loads(json.dumps(current))
    applied["reference_data"]["hazards"] = applied["reference_data"]["hazards"][:1]

    update = plan_pack_update(applied=applied, current=current)

    assert update.has_updates is True
    assert "Обрушение конструкций и грунта" in update.additions["hazards"]
