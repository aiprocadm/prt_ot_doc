"""Pure work-permit (наряд-допуск) lifecycle rules: FSM + value vocabularies.

No I/O / no sqlalchemy imports — mirrors ``domains/permits/lifecycle.py``.
All values are the canonical VARCHAR strings stored in the DB (see migration wp01).
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATUS_DRAFT = "draft"
STATUS_ISSUED = "issued"
STATUS_SUSPENDED = "suspended"
STATUS_CLOSED = "closed"
STATUS_CANCELLED = "cancelled"

WORK_PERMIT_STATUSES = frozenset({
    STATUS_DRAFT, STATUS_ISSUED, STATUS_SUSPENDED, STATUS_CLOSED, STATUS_CANCELLED,
})

# огневые / газоопасные / на высоте / замкнутое пространство / земляные / электро
WORK_TYPES = frozenset({
    "hot_work", "gas_hazardous", "height", "confined_space", "excavation", "electrical",
})

# выдающий наряд / ответственный руководитель / допускающий / производитель работ /
# наблюдающий / член бригады
MEMBER_ROLES = frozenset({
    "issuer", "supervisor", "admitter", "foreman", "observer", "member",
})

EVENT_TYPES = frozenset({
    "issued", "suspended", "resumed", "closed", "cancelled", "extended",
    "admitted", "member_added", "member_removed", "completion_recorded",
})

# системы обеспечения безопасности работ на высоте (782н):
# удерживающие / позиционирования / страховочные / для эвакуации и спасения /
# для подъёма и спуска (доступа)
SAFETY_SYSTEMS = frozenset({
    "restraint", "positioning", "fall_arrest", "rescue_evacuation", "access",
})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_ISSUED, STATUS_CANCELLED}),
    STATUS_ISSUED: frozenset({STATUS_SUSPENDED, STATUS_CLOSED, STATUS_CANCELLED}),
    STATUS_SUSPENDED: frozenset({STATUS_ISSUED, STATUS_CLOSED, STATUS_CANCELLED}),
    STATUS_CLOSED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}


class WorkPermitTransitionError(ValueError):
    """Invalid work-permit status transition (maps to HTTP 409)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid work-permit transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise WorkPermitTransitionError unless current -> target is allowed."""
    if current not in WORK_PERMIT_STATUSES or target not in WORK_PERMIT_STATUSES:
        raise WorkPermitTransitionError(current, target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise WorkPermitTransitionError(current, target)


def is_work_type(value: str) -> bool:
    return value in WORK_TYPES


def is_member_role(value: str) -> bool:
    return value in MEMBER_ROLES


def is_safety_system(value: str) -> bool:
    return value in SAFETY_SYSTEMS


# Роли подписи закрытия (782н): "сдал" — производитель работ; "принял" —
# ответственный руководитель ИЛИ допускающий.
HANDOVER_ROLES = frozenset({"foreman"})
ACCEPTANCE_ROLES = frozenset({"supervisor", "admitter"})
CLOSING_SIGNER_ROLES = HANDOVER_ROLES | ACCEPTANCE_ROLES


def role_to_closing_kind(role: str) -> str | None:
    """Вид подписи закрытия по роли члена бригады, либо None если роль не подписывает закрытие."""
    if role in HANDOVER_ROLES:
        return "handover"
    if role in ACCEPTANCE_ROLES:
        return "acceptance"
    return None


@dataclass(frozen=True)
class ClosingReadiness:
    can_close: bool
    missing: list[str] = field(default_factory=list)


def closing_readiness(*, completion_text: str | None, signed_kinds: set[str]) -> ClosingReadiness:
    """Готовность наряда к закрытию: акт оформлен + есть SIGNED «сдал» и «принял».

    Чистая функция (без I/O). ``signed_kinds`` — множество видов закрытия
    ({"handover","acceptance"}), у которых есть SIGNED-подпись.
    """
    missing: list[str] = []
    if not (completion_text and completion_text.strip()):
        missing.append("completion_act")
    if "handover" not in signed_kinds:
        missing.append("handover_signature")
    if "acceptance" not in signed_kinds:
        missing.append("acceptance_signature")
    return ClosingReadiness(can_close=not missing, missing=missing)


class WorkPermitClosingIncomplete(Exception):
    """close вызван до готовности гейта закрытия (maps to HTTP 409)."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"closing requirements not met: {missing}")
