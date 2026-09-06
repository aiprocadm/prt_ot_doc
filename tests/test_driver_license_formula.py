"""«Допущенный водитель» и «истёкшее удостоверение» — одна формула (BIZ-54-57 срез-88).

ЗАЧЕМ. Правило «считаются только допущенные к управлению, пустая дата — не
просрочка» писали заново цифры дисциплины (``discipline_numbers``), источник
``road_safety_driver`` календаря (``calendar_aggregator``) и подстановка
пакетов (``packs/prefill``); сводка внимания по портфелю клиентов (разд. 49.2)
удостоверений не знала вовсе — светофор клиента краснел, портфель молчал.
Срез-88: формула живёт в ``services/discipline_road_safety`` и одна.

ЧТО ПРОВЕРЯЕТСЯ: сторож — никто в ``backend/app`` не пишет условие «допущен»
по SQL сам; условия просрочки требуют дату и допуск.
"""

from __future__ import annotations

import pathlib
import re
from datetime import date

from app.services.discipline_road_safety import admitted_driver_where, expired_license_where

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Единственное место, где формула НАПИСАНА; остальные обязаны её импортировать.
FORMULA_HOME = "services/discipline_road_safety.py"

_CONDITION = re.compile(r'Driver\.status\s*==\s*"admitted"')


def test_сторож_условие_допущенный_водитель_пишется_один_раз() -> None:
    """Своя копия правила разойдётся с остальными на первой правке словаря статусов."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        if _CONDITION.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        "условие «допущенный водитель» написано заново — возьмите "
        f"admitted_driver_where из {FORMULA_HOME}: {offenders}"
    )


def test_просрочка_это_допуск_дата_и_срок_раньше_сегодня() -> None:
    today = date(2026, 9, 6)
    admitted = [str(c) for c in admitted_driver_where("t")]
    expired = [str(c) for c in expired_license_where("t", today)]
    assert len(admitted) == 3 and len(expired) == 5
    assert expired[:3] == admitted, "просрочка — это допущенный водитель плюс срок"
    assert any("license_due IS NOT NULL" in c for c in expired), "без даты — не просрочка"
    assert any("license_due <" in c for c in expired)
