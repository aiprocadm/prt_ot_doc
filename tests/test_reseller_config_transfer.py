"""Перенос конфигурации арендатора (BIZ-52 срез-16, Доп. №1 разд. 52.3)."""

from __future__ import annotations

import json
from pathlib import Path

from app.domains.reseller.config_transfer import (
    CONFIG_FORMAT_VERSION,
    build_config,
    check_config,
)
from app.domains.reseller.starter_pack import plan_starter_pack
from app.services.tenants.bootstrap.service import STARTER_PACK_ROOT


def _config(**overrides):
    base = dict(
        positions=["Директор", "Мастер"],
        hazards=["Падение с высоты"],
        controls=["Наряд-допуск"],
        source_slug="acme",
    )
    base.update(overrides)
    return build_config(**base)


def test_выгрузка_собирает_справочники():
    payload = _config().as_payload(pack="acme")

    assert payload["reference_data"]["positions"] == ["Директор", "Мастер"]
    assert payload["reference_data"]["hazards"] == ["Падение с высоты"]


def test_порядок_сохраняется():
    # Порядок задал человек: сначала частое, потом редкое. Сортировка по
    # алфавиту этот смысл потеряла бы.
    payload = _config(positions=["Мастер", "Директор", "Эколог"]).as_payload(pack="x")

    assert payload["reference_data"]["positions"] == ["Мастер", "Директор", "Эколог"]


def test_дубли_схлопываются_без_учёта_регистра():
    payload = _config(hazards=["Пожар", "пожар", " ПОЖАР "]).as_payload(pack="x")

    assert payload["reference_data"]["hazards"] == ["Пожар"]


def test_пустой_вид_в_выгрузку_не_попадает():
    # `"hazards": []` читается как «опасностей нет», а правда — «их не завели».
    payload = _config(hazards=[]).as_payload(pack="x")

    assert "hazards" not in payload["reference_data"]


def test_выгрузка_помнит_источник():
    # Через месяц человек спросит «откуда этот файл».
    assert _config().as_payload(pack="x")["exported_from"] == "acme"


def test_формат_совпадает_с_эталонным_набором():
    """Выгрузку можно положить в `seed/` и получить отраслевой набор.

    Второй формат означал бы два разбора и однажды — расхождение между «что
    применяется при выдаче» и «что переносится».
    """

    payload = _config().as_payload(pack="acme")
    reference = json.loads(
        (STARTER_PACK_ROOT / "v1" / "default.json").read_text(encoding="utf-8")
    )

    assert payload["version"] == reference["version"] == CONFIG_FORMAT_VERSION
    assert set(payload) >= {"version", "pack", "enabled_for", "reference_data"}


def test_выгрузка_применима_тем_же_разбором():
    # Главная проверка формата: план применения строится тем же кодом, что и
    # для файла из репозитория.
    plan = plan_starter_pack(_config().as_payload(pack="acme"))

    assert plan.apply["positions"] == ["Директор", "Мастер"]
    assert plan.apply["hazards"] == ["Падение с высоты"]


# --- разбор присланного файла -------------------------------------------------


def test_разбор_делит_виды_на_три_группы():
    check = check_config(
        {
            "reference_data": {
                "positions": ["Директор"],
                "briefing_types": ["Вводный"],
                "выдуманный": {"не": "список"},
            }
        }
    )

    assert check.applicable == {"positions": ["Директор"]}
    # Неприменимые названы: молчание читалось бы как потеря данных.
    assert check.skipped == ["briefing_types"]
    # Незнакомый ключ надо заметить: файл мог уйти вперёд кода.
    assert check.unknown == ["выдуманный"]


def test_пустой_файл_не_ломает_разбор():
    assert check_config({}).is_empty is True
    assert check_config({"reference_data": None}).is_empty is True


def test_файл_без_применимых_видов_считается_пустым():
    check = check_config({"reference_data": {"briefing_types": ["Вводный"]}})

    assert check.is_empty is True
    assert check.skipped == ["briefing_types"]


def test_дубли_в_присланном_файле_схлопываются():
    check = check_config({"reference_data": {"hazards": ["Пожар", "ПОЖАР", ""]}})

    assert check.applicable == {"hazards": ["Пожар"]}


def test_эталонные_файлы_разбираются_без_незнакомых_ключей():
    """Страж: файлы репозитория обязаны оставаться применимыми."""

    for path in sorted((STARTER_PACK_ROOT / "v1").glob("*.json")):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert check_config(payload).unknown == [], path.name
