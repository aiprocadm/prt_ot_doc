"""Сторож кодов ролей в маршрутах: список прав не обещает несуществующую роль (срез-151).

ЗАЧЕМ. Сверка прошлась по всем спискам ролей продукта и нашла девять кодов,
которых нет в ``RoleEnum``. Совпасть такой код не может ни с одним
пользователем, и поведение расходится с намерением, записанным в коде:

* ``workspace.py::_SAFETY_ROLES`` состоял из `safety_lead`, `safety_manager`,
  `admin`, `owner` — и разрез сводки «для специалистов по охране труда» не
  срабатывал НИ РАЗУ ни для одной реальной роли охраны труда: специалист ОТ,
  руководитель ОТиПБ, начальник отдела ОТ и инженер ПБ видели у себя нули по
  происшествиям и проверкам. То же с мёртвым `hr_manager` в ``_HR_ROLES``;
* ``contractors.py`` обещал доступ `hse_head` и `hse_specialist`,
  ``external_registry.py``, ``integration_readiness.py`` и ``webhooks.py`` —
  роли `integrations`. Все они мертвы: фактические права были уже обещанных.

Тест проверяет ТОЛЬКО существование кодов. Он намеренно не судит, каким
ролям что положено: это решение о безопасности, а не о правописании.

Область: константы вида ``*_ROLES`` (имя в верхнем регистре — так пишут
списки прав) и списки, переданные прямо в ``rbac(...)``/``abac(...)``.
Локальные переменные в нижнем регистре не берутся: например
``guarded_roles`` в модуле файлов перечисляет НАЗНАЧЕНИЯ файлов
(`output`, `signature`, `receipt`), а не роли пользователей.
"""

from __future__ import annotations

import ast
import pathlib

from app.models.models import RoleEnum

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNED_ROOTS = (
    REPO_ROOT / "backend" / "app" / "api",
    REPO_ROOT / "backend" / "app" / "modules",
)

KNOWN_ROLE_CODES = {role.value for role in RoleEnum}


def _role_literals() -> dict[str, set[str]]:
    """Код роли → где он встречается («файл:строка имя»)."""

    found: dict[str, set[str]] = {}

    def remember(value: str, where: str) -> None:
        found.setdefault(value, set()).add(where)

    def strings(node: ast.AST) -> list[str]:
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [
                e.value
                for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
        return []

    for root in SCANNED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO_ROOT)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    # Списки прав пишут константами: _INCIDENT_READ_ROLES, _ROLES…
                    constants = [n for n in names if n.upper() == n and n.upper().endswith("ROLES")]
                    for value in strings(node.value) if constants else []:
                        remember(value, f"{rel}:{node.lineno} {constants[0]}")
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    if name in {"rbac", "abac"}:
                        candidates = list(node.args) + [
                            kw.value for kw in node.keywords if kw.arg == "required_roles"
                        ]
                        for candidate in candidates:
                            for value in strings(candidate):
                                remember(value, f"{rel}:{node.lineno} {name}(...)")
    return found


def test_в_списках_прав_нет_несуществующих_ролей() -> None:
    found = _role_literals()
    assert found, "не нашлось ни одного списка ролей — проверка потеряла область"
    unknown = {code: places for code, places in found.items() if code not in KNOWN_ROLE_CODES}
    assert not unknown, (
        "коды ролей вне RoleEnum (совпасть не могут, доступ уже обещанного):\n"
        + "\n".join(
            f"  {code!r}: " + ", ".join(sorted(places)) for code, places in sorted(unknown.items())
        )
    )


def test_сводка_роли_знает_настоящие_роли_охраны_труда() -> None:
    """Разрез сводки обязан срабатывать для ролей, ради которых написан."""

    from app.api.routes.workspace import _HR_ROLES, _MANAGER_ROLES, _SAFETY_ROLES

    for group in (_SAFETY_ROLES, _HR_ROLES, _MANAGER_ROLES):
        assert group <= KNOWN_ROLE_CODES, sorted(group - KNOWN_ROLE_CODES)
    # Профильные роли охраны труда и пожарной безопасности — в разрезе ОТ.
    assert {"ot_specialist", "ot_pb_lead", "ot_head", "pb_engineer"} <= _SAFETY_ROLES
    assert "hr" in _HR_ROLES
