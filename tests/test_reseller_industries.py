"""Отраслевые наборы (BIZ-52 срез-12, Доп. №1 разд. 52.3).

Правила выбора набора плюс проверка САМИХ ФАЙЛОВ: набор, который не читается
или назван не так, отличается от отсутствующего только моментом, когда это
выяснится — при заведении клиента.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domains.reseller.industries import (
    DEFAULT_INDUSTRY,
    INDUSTRIES,
    UnknownIndustryError,
    pack_name_for,
    resolve_industry,
)
from app.domains.reseller.starter_pack import plan_starter_pack
from app.services.tenants.bootstrap.service import STARTER_PACK_ROOT


def test_отрасль_выбирает_свой_набор():
    assert pack_name_for(industry="construction", demo=False) == "construction"
    assert pack_name_for(industry="transport", demo=False) == "transport"


def test_без_отрасли_прежний_общий_набор():
    # Поведение до этого среза не должно измениться ни на строку.
    assert pack_name_for(industry=None, demo=False) == "default"
    assert pack_name_for(industry="", demo=False) == "default"


def test_демонстрационный_набор_перекрывает_отрасль():
    # Иначе на каждую отрасль понадобился бы ещё и демо-вариант: файлов вчетверо
    # больше ради сценария, которого никто не просил.
    assert pack_name_for(industry="energy", demo=True) == "demo"


def test_отрасль_проверяется_даже_с_демо():
    # Опечатка не должна оставаться незамеченной только потому, что в этот раз
    # она ни на что не повлияла.
    with pytest.raises(UnknownIndustryError):
        pack_name_for(industry="строительство", demo=True)


def test_регистр_и_пробелы_не_мешают():
    assert resolve_industry("  Construction ").code == "construction"


def test_неизвестная_отрасль_это_отказ_а_не_общий_набор():
    # Тихий откат означал бы: партнёр думает, что завёл стройку, а клиент
    # получил общий набор — и узнает об этом сам.
    with pytest.raises(UnknownIndustryError) as exc:
        resolve_industry("mining")

    assert "mining" in str(exc.value)


def test_общая_отрасль_идёт_первой():
    # Она подходит любому; список читают сверху вниз.
    assert INDUSTRIES[0].code == DEFAULT_INDUSTRY


def test_коды_отраслей_не_повторяются():
    codes = [item.code for item in INDUSTRIES]

    assert len(codes) == len(set(codes))


# --- сами файлы наборов -------------------------------------------------------


def _pack_path(name: str) -> Path:
    return STARTER_PACK_ROOT / "v1" / f"{name}.json"


def test_у_каждой_отрасли_есть_файл_набора():
    # Страж: добавить отрасль в список и забыть файл — значит сломать заведение
    # клиента этой отрасли, и узнать об этом от партнёра.
    missing = [item.code for item in INDUSTRIES if not _pack_path(item.pack).exists()]

    assert missing == []


@pytest.mark.parametrize("industry", INDUSTRIES, ids=lambda item: item.code)
def test_набор_читается_и_даёт_справочники(industry):
    payload = json.loads(_pack_path(industry.pack).read_text(encoding="utf-8"))
    plan = plan_starter_pack(payload)

    # Набор без применимых строк бесполезен: ради них он и существует.
    assert plan.apply.get("positions"), industry.code
    assert plan.apply.get("hazards"), industry.code
    assert plan.apply.get("controls"), industry.code
    # Незнакомые ключи означают, что файл ушёл вперёд кода, — это надо заметить.
    assert plan.unknown == [], industry.code


@pytest.mark.parametrize("industry", INDUSTRIES, ids=lambda item: item.code)
def test_имя_набора_внутри_файла_совпадает_с_именем_файла(industry):
    # Разойдись они — отчёт о применении назвал бы не тот набор, что применён.
    payload = json.loads(_pack_path(industry.pack).read_text(encoding="utf-8"))

    assert payload["pack"] == industry.pack


def test_отраслевые_наборы_отличаются_от_общего():
    # Одинаковое содержимое означало бы, что отрасль выбрана, а разницы нет.
    general = json.loads(_pack_path("default").read_text(encoding="utf-8"))
    for item in INDUSTRIES:
        if item.code == DEFAULT_INDUSTRY:
            continue
        payload = json.loads(_pack_path(item.pack).read_text(encoding="utf-8"))
        assert (
            payload["reference_data"]["hazards"] != general["reference_data"]["hazards"]
        ), item.code
