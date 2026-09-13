"""Сторож словарей происшествий и проверок: экран и сервер знают одни значения (срез-150).

ЗАЧЕМ. Сверка нашла два дефекта одного класса — «список значений написан в
коде экрана руками, и сверять его было нечем»:

* **происшествия**: форма предлагала семь видов (`near_miss`, `micro_trauma`,
  `injury`, `fatal`, `fire`, `environmental`, `other`), из которых сервер
  (``IncidentType``) принимает ОДИН — `near_miss`. «Несчастный случай»
  (`accident`), микротравму (`microtrauma`, без подчёркивания) и опасное
  состояние (`unsafe_condition`) завести было нельзя вовсе, а выбор «Травма»
  или «Пожар» кончался 422. Тяжесть предлагала `critical`, которого у
  ``IncidentSeverity`` нет;
* **проверки**: форма предлагала пять видов (`planned`, `unplanned`,
  `documentary`, `on_site`, `counter`) — пересечение с ``InspectionType``
  (`internal`, `external`) ПУСТОЕ: создать проверку через форму было
  невозможно при любом выборе. Статус `cancelled` фронту известен не был.

Тот же класс закрывал срез-148 (роли получателей уведомлений) — и там
лекарство то же: один словарь и сторож равенства составов. Здесь словарь
живёт на фронте (значения закрытые, их единицы, и они уже приходят в каждом
ответе API), а равенство держит этот тест — он читает исходники витрины и
сверяет их с перечислениями сервера.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.incidents import IncidentSeverity, IncidentStatus, IncidentType
from app.models.inspections import InspectionStatus, InspectionType

REPO_ROOT = Path(__file__).resolve().parents[1]
INCIDENTS_API = REPO_ROOT / "frontend" / "src" / "api" / "incidents.ts"
INSPECTIONS_API = REPO_ROOT / "frontend" / "src" / "api" / "inspections.ts"
INCIDENTS_PAGE = REPO_ROOT / "frontend" / "src" / "pages" / "incidents" / "IncidentsPage.tsx"
INSPECTIONS_PAGE = REPO_ROOT / "frontend" / "src" / "pages" / "inspections" / "InspectionsPage.tsx"
EMPLOYEE_CARD = REPO_ROOT / "frontend" / "src" / "pages" / "employees" / "EmployeeCardPage.tsx"


def _labels(path: Path, name: str) -> dict[str, str]:
    """Ключи и подписи объявленного во фронте словаря ``name``."""

    source = path.read_text(encoding="utf-8")
    block = re.search(
        rf"export const {name}: Record<string, string> = \{{(.*?)\}};",
        source,
        re.S,
    )
    assert block is not None, f"{name} не найден в {path.name}"
    return dict(re.findall(r'(\w+): "([^"]+)"', block.group(1)))


@pytest.mark.parametrize(
    ("path", "name", "enum_cls"),
    [
        (INCIDENTS_API, "INCIDENT_TYPE_LABELS", IncidentType),
        (INCIDENTS_API, "INCIDENT_SEVERITY_LABELS", IncidentSeverity),
        (INCIDENTS_API, "INCIDENT_STATUS_LABELS", IncidentStatus),
        (INSPECTIONS_API, "INSPECTION_TYPE_LABELS", InspectionType),
        (INSPECTIONS_API, "INSPECTION_STATUS_LABELS", InspectionStatus),
    ],
)
def test_словарь_витрины_совпадает_с_перечислением_сервера(path, name, enum_cls) -> None:
    labels = _labels(path, name)
    expected = {item.value for item in enum_cls}
    assert set(labels) == expected, (
        f"{name} разошёлся с {enum_cls.__name__}: "
        f"лишние {sorted(set(labels) - expected)}, "
        f"недостающие {sorted(expected - set(labels))}"
    )
    # Подпись обязана быть человеческой: код латиницей в выпадающем списке —
    # то же самое, что отсутствие подписи (разд. 60.1 «без жаргона»).
    for code, label in labels.items():
        assert label.strip(), f"{name}: пустая подпись у {code!r}"
        assert label != code, f"{name}: подпись {code!r} — это сам код"


@pytest.mark.parametrize(
    ("path", "forbidden"),
    [
        (INCIDENTS_PAGE, ("INCIDENT_TYPES", "INCIDENT_TYPE_LABELS", "SEVERITY_LEVELS")),
        (INSPECTIONS_PAGE, ("INSPECTION_TYPES", "INSPECTION_TYPE_LABELS")),
        (EMPLOYEE_CARD, ("INCIDENT_TYPE_LABELS", "INCIDENT_SEVERITY_LABELS")),
    ],
)
def test_экран_не_заводит_свой_список_значений(path: Path, forbidden: tuple[str, ...]) -> None:
    """Регрессия: словарь снова объявлен в коде экрана — значит, он снова
    разъедется с сервером, и сторож выше его не увидит."""

    source = path.read_text(encoding="utf-8")
    for name in forbidden:
        assert not re.search(rf"^const {name}\b", source, re.M), (
            f"{path.name}: {name} объявлен на экране — словарь должен приходить "
            f"из @/api/incidents или @/api/inspections одним на продукт"
        )
