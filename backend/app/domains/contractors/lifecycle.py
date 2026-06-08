"""Pure contractor-admission readiness rules (no I/O).

A contractor employee has three requirements — access, training, medical —
each evaluated from a manual status flag cross-checked against a deadline.
The cross-check is the point of this engine: a stale ``valid`` status whose
deadline has passed must NOT count as ready.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.domains.shared import ContingentItemStatus, classify
from app.modules.contractors.models import ComplianceStatus

TRAINING_INTERVAL_DAYS = 365  # срок годности обучения (константа правила, не колонка БД)

_BLOCKING_STATUSES = {ComplianceStatus.EXPIRED, ComplianceStatus.BLOCKED}
_BLOCKING_DEADLINES = {ContingentItemStatus.OVERDUE, ContingentItemStatus.MISSING}
_WARNING_DEADLINES = {ContingentItemStatus.DUE_SOON}


class ReadinessStatus(str, enum.Enum):
    ALLOWED = "allowed"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class EmployeeVerdict:
    employee_id: str
    status: ReadinessStatus
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _as_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


def _assess(requirement: str, status: ComplianceStatus, deadline: ContingentItemStatus | None,
            violations: list[str], warnings: list[str]) -> None:
    """Fold one requirement (status flag + optional deadline) into the verdict lists."""
    blocked = status in _BLOCKING_STATUSES or (deadline in _BLOCKING_DEADLINES)
    if blocked:
        violations.append(requirement)
        return
    if status == ComplianceStatus.PENDING or (deadline in _WARNING_DEADLINES):
        warnings.append(requirement)


def evaluate_employee(emp, today: date) -> EmployeeVerdict:
    """Compute the readiness verdict for a contractor employee."""
    violations: list[str] = []
    warnings: list[str] = []

    # access: status only, no deadline
    _assess("access", emp.access_status, None, violations, warnings)

    # training: deadline = last_training_at + TRAINING_INTERVAL_DAYS
    last_training = _as_date(emp.last_training_at)
    training_deadline = (
        classify(last_training + timedelta(days=TRAINING_INTERVAL_DAYS), today)
        if last_training is not None
        else ContingentItemStatus.MISSING
    )
    _assess("training", emp.training_status, training_deadline, violations, warnings)

    # medical: explicit deadline next_medical_at
    medical_deadline = classify(_as_date(emp.next_medical_at), today)
    _assess("medical", emp.medical_status, medical_deadline, violations, warnings)

    if violations:
        status = ReadinessStatus.BLOCKED
    elif warnings:
        status = ReadinessStatus.WARNING
    else:
        status = ReadinessStatus.ALLOWED
    return EmployeeVerdict(employee_id=emp.id, status=status, violations=violations, warnings=warnings)
