"""Группы по электробезопасности (903н): резолв текущей группы персоны + готовность бригады.

Чистый модуль (без I/O / без sqlalchemy) — как lifecycle.py / profiles.py. Группа живёт
в Person.qualifications (kind="electrical_safety_group", level ∈ I..V). Read-путь наряда
обогащает членов резолвнутой группой и считает мягкую готовность.
"""

from __future__ import annotations

from datetime import date, datetime

GROUP_ORDER = ["I", "II", "III", "IV", "V"]

# Минимумы 903н до 1000В (le_1000) — текущий/дефолтный набор.
ROLE_MIN_GROUP: dict[str, str] = {
    "issuer": "IV",
    "supervisor": "IV",
    "admitter": "IV",
    "foreman": "III",
    "member": "III",
    "observer": "III",
}

# Минимумы выше 1000В (ПОТЭЭ; сверить с юристом).
ROLE_MIN_GROUP_HV: dict[str, str] = {
    "issuer": "IV",
    "supervisor": "V",
    "admitter": "IV",
    "foreman": "IV",
    "member": "III",
    "observer": "IV",
}

_KIND = "electrical_safety_group"


def rank(level: str | None) -> int:
    if level in GROUP_ORDER:
        return GROUP_ORDER.index(level)
    return -1


def _as_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _min_table(voltage_level: str | None) -> dict[str, str]:
    return ROLE_MIN_GROUP_HV if voltage_level == "gt_1000" else ROLE_MIN_GROUP


def role_min(role: str, voltage_level: str | None = None) -> str | None:
    return _min_table(voltage_level).get(role)


def current_group(qualifications: list[dict] | None, as_of: date) -> str | None:
    best: str | None = None
    for q in qualifications or []:
        if not isinstance(q, dict) or q.get("kind") != _KIND:
            continue
        level = q.get("level")
        if rank(level) < 0:
            continue
        vu = _as_date(q.get("valid_until"))
        if vu is not None and vu < as_of:
            continue  # истекла
        if best is None or rank(level) > rank(best):
            best = level
    return best


def meets_minimum(group: str | None, role: str, voltage_level: str | None = None) -> bool:
    required = _min_table(voltage_level).get(role)
    if required is None:
        return True
    return rank(group) >= rank(required)


def readiness(members: list[dict], voltage_level: str | None = None) -> dict:
    table = _min_table(voltage_level)
    insufficient = []
    for m in members:
        role = m.get("role")
        group = m.get("group")
        if not meets_minimum(group, role, voltage_level):
            insufficient.append(
                {
                    "person_id": m.get("person_id"),
                    "role": role,
                    "group": group,
                    "required": table.get(role),
                }
            )
    return {"ok": not insufficient, "insufficient": insufficient}
