"""«Допущенный водитель» и «истёкшее удостоверение» — одна формула (BIZ-54-57 срез-88).

ЗАЧЕМ. Правило «считаются только допущенные к управлению, пустая дата — не
просрочка» писали заново цифры дисциплины (``discipline_numbers``), источник
``road_safety_driver`` календаря (``calendar_aggregator``) и подстановка
пакетов (``packs/prefill``); сводка внимания по портфелю клиентов (разд. 49.2)
удостоверений не знала вовсе — светофор клиента краснел, портфель молчал.
Срез-88: формула живёт в ``services/discipline_road_safety`` и одна.

ЧТО ПРОВЕРЯЕТСЯ: сторож — никто в ``backend/app`` не пишет условие «допущен»
ни по SQL, ни по уже загруженной записи; условия просрочки требуют дату и
допуск.

Срез-129: сторож SQL-формы был КРАСНЫМ на ``main`` — сводка контура БДД
(``modules/road_safety/api.py``) писала условие своей копией; приехало это со
срезом-123 и не было замечено, потому что срезы 123–126 закрывались прицельной
регрессией без полного прогона. Заодно нашлась вторая форма той же копии:
сравнение состояния у ЗАГРУЖЕННОГО водителя (``driver.status != "admitted"``)
перед выпиской путевого листа — его сторож не ловил вовсе.
"""

from __future__ import annotations

import pathlib
import re
from datetime import date

from app.services.discipline_road_safety import (
    admitted_driver_where,
    expired_license_where,
    is_admitted,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Единственное место, где формула НАПИСАНА; остальные обязаны её импортировать.
FORMULA_HOME = "services/discipline_road_safety.py"

_CONDITION = re.compile(r'Driver\.status\s*==\s*"admitted"')
#: Срез-129: та же формула у уже загруженной записи. Для неё есть
#: ``is_admitted``; сравнение строкой — вторая копия правила, только другой
#: формы (тот же приём, что у ``person_scope.is_employed``).
_OBJECT_CONDITION = re.compile(r'\.status\s*[!=]=\s*"admitted"')


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


def test_сторож_допуск_у_загруженной_записи_тоже_не_пишут_руками() -> None:
    """Строковое сравнение состояния — та же копия правила, только другой формы.

    Оно опаснее SQL-копии: словарь состояний водителя живёт в
    ``core/disciplines``, и переименование значения сломает выписку путевых
    листов молча — запрос при этом останется верным.
    """

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        if _OBJECT_CONDITION.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        "состояние «допущен» сравнивают у загруженной записи — возьмите "
        f"is_admitted из {FORMULA_HOME}: {offenders}"
    )


def test_допущен_это_не_удалён_и_состояние_допуска() -> None:
    """``is_admitted`` — та же формула для уже загруженной записи."""

    from datetime import datetime, timezone

    from app.models.road_safety import Driver

    assert is_admitted(Driver(status="admitted"))
    assert not is_admitted(Driver(status="suspended"))
    assert not is_admitted(Driver(status="admitted", deleted_at=datetime.now(tz=timezone.utc)))


def test_просрочка_это_допуск_дата_и_срок_раньше_сегодня() -> None:
    today = date(2026, 9, 6)
    admitted = [str(c) for c in admitted_driver_where("t")]
    expired = [str(c) for c in expired_license_where("t", today)]
    assert len(admitted) == 3 and len(expired) == 5
    assert expired[:3] == admitted, "просрочка — это допущенный водитель плюс срок"
    assert any("license_due IS NOT NULL" in c for c in expired), "без даты — не просрочка"
    assert any("license_due <" in c for c in expired)
