"""Одно право на запись у контуров дисциплин (BIZ-54-57 срез-119).

До этого среза список ролей, которым разрешена запись, был написан пять раз —
по копии в каждом модуле дисциплины, — а экран проверял СВОЙ список прав,
никак не связанный с серверным. Расхождение было не теоретическим: сервер
пускал специалиста по охране труда вести записи всех пяти контуров, а экраны
этих контуров ему не показывались вовсе; роль «Эколог» не видела экологию.

Сторож связывает две стороны: кому сервер разрешает запись — тому экран обязан
дать право ``<модуль>.manage``, и наоборот.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.disciplines import Discipline, discipline_write_roles
from app.modules.subscription.registry import MODULE_REGISTRY

#: Пять собственных контуров дисциплин: дисциплина ↔ код модуля.
CONTOURS: dict[Discipline, str] = {
    Discipline.FIRE_SAFETY: "fire_safety",
    Discipline.INDUSTRIAL_SAFETY: "industrial_safety",
    Discipline.ECOLOGY: "ecology",
    Discipline.CIVIL_DEFENSE: "civil_defense",
    Discipline.ROAD_SAFETY: "road_safety",
}

#: Одна и та же роль называется на сервере и на экране по-разному
#: (`frontend/src/permissions/ability.ts`, ROLE_ALIASES).
ROLE_ALIASES: dict[str, str] = {"ot_pb_lead": "ot_pb_head"}

_PERMISSIONS_TS = Path("frontend/src/permissions/permissions.ts")


def _screen_permission_codes() -> dict[str, str]:
    """Каталог прав экрана: ИМЯ → код."""

    source = _PERMISSIONS_TS.read_text(encoding="utf-8")
    block = re.search(r"export const PERMISSIONS = \{(.*?)\n\} as const;", source, re.S)
    assert block is not None, "каталог PERMISSIONS не найден"
    return dict(re.findall(r"(\w+): \"([^\"]+)\"", block.group(1)))


def _named_list(source: str, name: str) -> list[str]:
    block = re.search(rf"const {name}: Permission\[\] = \[(.*?)\n\];", source, re.S)
    assert block is not None, f"список {name} не найден"
    return re.findall(r"PERMISSIONS\.(\w+)", block.group(1))


def _screen_role_permissions() -> dict[str, set[str]]:
    """Права ролей на экране: роль → множество ИМЁН прав."""

    source = _PERMISSIONS_TS.read_text(encoding="utf-8")
    catalogue = _screen_permission_codes()
    base_ops = _named_list(source, "baseOpsPermissions")

    block = re.search(
        r"export const ROLE_PERMISSIONS: Record<Role, Permission\[\]> = \{\n(.*?)\n\};",
        source,
        re.S,
    )
    assert block is not None, "карта ROLE_PERMISSIONS не найдена"

    entries: dict[str, str] = {}
    current: str | None = None
    for line in block.group(1).split("\n"):
        started = re.match(r"^  (\w+): ", line)
        if started:
            current = started.group(1)
            entries[current] = ""
        if current is not None:
            entries[current] += line + "\n"

    result: dict[str, set[str]] = {}
    for role, text in entries.items():
        if "ALL_PERMISSIONS" in text:
            # `ALL_PERMISSIONS` и `ALL_PERMISSIONS.filter(... !== PERMISSIONS.X)`.
            excluded = set(re.findall(r"!== PERMISSIONS\.(\w+)", text))
            result[role] = set(catalogue) - excluded
            continue
        names = set(re.findall(r"PERMISSIONS\.(\w+)", text))
        if "...baseOpsPermissions" in text:
            names |= set(base_ops)
        result[role] = names
    return result


@pytest.mark.parametrize("discipline,code", sorted(CONTOURS.items(), key=lambda i: i[1]))
def test_экран_даёт_право_записи_тем_же_ролям_что_и_сервер(
    discipline: Discipline, code: str
) -> None:
    """Кому сервер разрешает запись — тому экран обязан дать `<модуль>.manage`."""

    catalogue = _screen_permission_codes()
    by_code = {value: name for name, value in catalogue.items()}
    manage = by_code.get(f"{code}.manage")
    assert manage is not None, f"в каталоге экрана нет права {code}.manage"

    on_screen = _screen_role_permissions()
    granted = {role for role, names in on_screen.items() if manage in names}
    expected = {ROLE_ALIASES.get(role, role) for role in discipline_write_roles(discipline)}
    assert granted == expected, f"{code}: сервер и экран расходятся в праве на запись"


@pytest.mark.parametrize("discipline,code", sorted(CONTOURS.items(), key=lambda i: i[1]))
def test_право_записи_не_бывает_без_права_видеть(discipline: Discipline, code: str) -> None:
    """Право вести записи без права открыть экран — право, которым не воспользуешься."""

    catalogue = _screen_permission_codes()
    by_code = {value: name for name, value in catalogue.items()}
    manage, view = by_code[f"{code}.manage"], by_code[f"{code}.view"]
    for role, names in _screen_role_permissions().items():
        if manage in names:
            assert view in names, f"{role}: есть {code}.manage, но нет {code}.view"


@pytest.mark.parametrize("discipline,code", sorted(CONTOURS.items(), key=lambda i: i[1]))
def test_право_записи_объявлено_в_реестре_модулей(discipline: Discipline, code: str) -> None:
    """Код права должен быть известен платформе, а не жить только на экране."""

    module = next(m for m in MODULE_REGISTRY if m.code == code)
    assert f"{code}.view" in module.permissions, code
    assert f"{code}.manage" in module.permissions, code


@pytest.mark.parametrize("discipline,code", sorted(CONTOURS.items(), key=lambda i: i[1]))
def test_модуль_не_объявляет_свой_список_ролей(discipline: Discipline, code: str) -> None:
    """Пять копий одного списка держатся вместе ровно до первой правки."""

    source = Path(f"backend/app/modules/{code}/api.py").read_text(encoding="utf-8")
    assert f"_ROLES = list(discipline_write_roles(Discipline.{discipline.name}))" in source, code
    assert '_ROLES = ["' not in source, f"{code}: список ролей снова написан руками"


def test_профильная_роль_названа_только_там_где_она_есть() -> None:
    """Роль дисциплины нельзя выдумать: у ПромБеза, ГО-ЧС и БДД её в продукте нет."""

    from app.core.disciplines import DISCIPLINE_SPECIALIST_ROLE
    from app.models.tenant_billing import RoleEnum

    known = {r.value for r in RoleEnum}
    for discipline, role in DISCIPLINE_SPECIALIST_ROLE.items():
        assert role in known, f"{discipline}: роли {role!r} нет в продукте"
    assert set(DISCIPLINE_SPECIALIST_ROLE) == {Discipline.ECOLOGY, Discipline.FIRE_SAFETY}
