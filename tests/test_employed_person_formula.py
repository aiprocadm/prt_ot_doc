"""«Уволенный не в счёт» — одна формула на всех, кто считает людей (BIZ-54-57 срез-89).

ЗАЧЕМ. Условие «не удалён и не уволен» писали пять мест (площадка 360° ×2,
светофор клиента, сводка ПБ, сигнал удостоверений), а сигналы медосмотров,
СИЗ, обучения и контактов в сводке внимания по портфелю (разд. 49.2)
уволенных считали — портфель горел там, где светофор того же клиента был
чист. Срез-89: формула живёт в ``services/person_scope`` и одна.

ЧТО ПРОВЕРЯЕТСЯ: сторож — никто в ``backend/app`` не пишет условие
«не уволен» по SQL сам; состав условий. Срез-95: и условие на запись
(``not_in(not_employed_person_ids(...))``) собирает только ``person_scope`` —
иначе где-то забудут про пустой ``person_id``, и запись без человека пропадёт.
"""

from __future__ import annotations

import pathlib
import re

from app.models.briefings import BriefingEntry
from app.models.medical import MedicalExam
from app.services.person_scope import (
    employed_person_where,
    employed_record_where,
    not_employed_person_ids,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Единственное место, где формула НАПИСАНА; остальные обязаны её импортировать.
FORMULA_HOME = "services/person_scope.py"

_CONDITION = re.compile(r"employment_status\s*!=\s*(EmploymentStatus\.TERMINATED|\"terminated\")")
_RECORD_CONDITION = re.compile(r"\.(not_in|in_)\(\s*not_employed_person_ids\(")


def test_сторож_условие_не_уволен_пишется_один_раз() -> None:
    """Своя копия правила разойдётся с остальными на первой правке словаря статусов."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        if _CONDITION.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        "условие «не уволен» написано заново — возьмите "
        f"employed_person_where из {FORMULA_HOME}: {offenders}"
    )


def test_работающий_это_не_удалён_и_не_уволен() -> None:
    conditions = [str(c) for c in employed_person_where()]
    assert len(conditions) == 2
    assert any("deleted_at IS NULL" in c for c in conditions)
    assert any("employment_status !=" in c for c in conditions)


def test_кого_не_считать_это_отрицание_той_же_формулы() -> None:
    """Срез-93: подзапрос для мест без join'а с Person строится из формулы, а не заново."""

    sql = str(not_employed_person_ids("tenant-1").compile(compile_kwargs={"literal_binds": True}))
    assert "person.tenant_id = 'tenant-1'" in sql
    assert "NOT (person.deleted_at IS NULL AND person.employment_status !=" in sql


def test_сторож_условие_на_запись_собирает_только_person_scope() -> None:
    """Срез-95: ``Model.person_id.not_in(not_employed_person_ids(...))`` руками — снова
    копии, только другой формы; берите ``employed_record_where``."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        if _RECORD_CONDITION.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        "условие на запись написано заново — возьмите "
        f"employed_record_where из {FORMULA_HOME}: {offenders}"
    )


def test_условие_на_запись_помнит_про_пустой_person_id() -> None:
    """Обязательный ``person_id`` — только NOT IN; необязательный — и записи без человека."""

    strict = str(
        employed_record_where(MedicalExam, "tenant-1").compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    loose = str(
        employed_record_where(BriefingEntry, "tenant-1").compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert strict.startswith("(medical_exam.person_id NOT IN (SELECT person.id")
    assert "person.tenant_id = 'tenant-1'" in strict
    assert "NOT (person.deleted_at IS NULL AND person.employment_status !=" in strict
    assert loose.startswith(
        "briefing_entries.person_id IS NULL OR (briefing_entries.person_id NOT IN"
    )
