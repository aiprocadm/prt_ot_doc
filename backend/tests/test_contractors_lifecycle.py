from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from app.modules.contractors.models import ComplianceStatus
from app.domains.contractors.lifecycle import (
    ReadinessStatus,
    evaluate_employee,
    TRAINING_INTERVAL_DAYS,
)


@dataclass
class _Emp:
    id: str = "e1"
    access_status: ComplianceStatus = ComplianceStatus.VALID
    training_status: ComplianceStatus = ComplianceStatus.VALID
    medical_status: ComplianceStatus = ComplianceStatus.VALID
    last_training_at: datetime | None = None
    next_medical_at: datetime | None = None


TODAY = datetime(2026, 6, 8, tzinfo=timezone.utc).date()


def _dt(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def test_all_valid_recent_is_allowed():
    emp = _Emp(
        last_training_at=_dt(TODAY),
        next_medical_at=_dt(TODAY + timedelta(days=200)),
    )
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.ALLOWED
    assert v.violations == []


def test_stale_valid_medical_is_blocked():
    emp = _Emp(
        last_training_at=_dt(TODAY),
        next_medical_at=_dt(TODAY - timedelta(days=1)),
    )
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.BLOCKED
    assert "medical" in v.violations


def test_expired_status_is_blocked():
    emp = _Emp(access_status=ComplianceStatus.EXPIRED, last_training_at=_dt(TODAY),
               next_medical_at=_dt(TODAY + timedelta(days=200)))
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.BLOCKED
    assert "access" in v.violations


def test_missing_deadlines_are_blocked():
    emp = _Emp(last_training_at=None, next_medical_at=None)
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.BLOCKED
    assert set(v.violations) >= {"training", "medical"}


def test_pending_status_is_warning():
    emp = _Emp(training_status=ComplianceStatus.PENDING, last_training_at=_dt(TODAY),
               next_medical_at=_dt(TODAY + timedelta(days=200)))
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.WARNING
    assert "training" in v.warnings


def test_due_soon_deadline_is_warning():
    emp = _Emp(last_training_at=_dt(TODAY),
               next_medical_at=_dt(TODAY + timedelta(days=10)))
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.WARNING
    assert "medical" in v.warnings


def test_training_interval_constant_is_one_year():
    assert TRAINING_INTERVAL_DAYS == 365
