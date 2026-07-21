"""Чистый FSM заявки на возмещение СФР (§12.4 срез-2).

Без I/O и без sqlalchemy — зеркало app/domains/permits/lifecycle.py и
app/domains/work_permits/lifecycle.py. Значения статусов — канонические VARCHAR
из budget_reimbursement.status (нижний регистр, см. миграцию bg02).

Цепочка из дизайна среза: черновик -> подана -> одобрена/отклонена -> выплачена.
Отклонённая и выплаченная заявки терминальны (пересдача = новая заявка).
"""

from __future__ import annotations

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_PAID = "paid"

REIMBURSEMENT_STATUSES = frozenset(
    {STATUS_DRAFT, STATUS_SUBMITTED, STATUS_APPROVED, STATUS_REJECTED, STATUS_PAID}
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_SUBMITTED}),
    STATUS_SUBMITTED: frozenset({STATUS_APPROVED, STATUS_REJECTED}),
    STATUS_APPROVED: frozenset({STATUS_PAID}),
    STATUS_REJECTED: frozenset(),
    STATUS_PAID: frozenset(),
}

# Состав и реквизиты заявки редактируются только в черновике: после подачи
# заявка — документ, отправленный во внешний орган.
EDITABLE_STATUSES = frozenset({STATUS_DRAFT})

# action (роут POST /{id}/{action}) -> целевой статус
ACTION_TARGETS: dict[str, str] = {
    "submit": STATUS_SUBMITTED,
    "approve": STATUS_APPROVED,
    "reject": STATUS_REJECTED,
    "pay": STATUS_PAID,
}


class ReimbursementTransitionError(ValueError):
    """Недопустимый переход статуса заявки (маппится в HTTP 409 на уровне API)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid reimbursement transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    if current not in REIMBURSEMENT_STATUSES or target not in REIMBURSEMENT_STATUSES:
        raise ReimbursementTransitionError(current, target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ReimbursementTransitionError(current, target)


def ensure_editable(current: str) -> None:
    """Правка/состав разрешены только в черновике (тот же класс ошибки -> 409)."""
    if current not in EDITABLE_STATUSES:
        raise ReimbursementTransitionError(current, STATUS_DRAFT)
