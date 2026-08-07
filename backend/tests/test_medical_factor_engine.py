"""Pure-function tests for the §9.2 factor-driven engine."""

from app.domains.medical.lifecycle import (
    FactorTuple,
    factors_for_hazards,
    required_exams_from_factors,
    worst_status,
)
from app.models.models import MedicalExamKind as K

NOISE: FactorTuple = ("4.4", "Шум", (K.PERIODIC,), 12)
CHEM: FactorTuple = ("1.1", "Химические", (K.PERIODIC, K.FLUOROGRAPHY), 24)
HEIGHT: FactorTuple = ("6.1", "Работы на высоте", (K.PERIODIC,), 12)
CATALOG = [NOISE, CHEM, HEIGHT]


def test_factors_for_hazards_selects_mapped_codes():
    assert factors_for_hazards({"4.4", "1.1"}, CATALOG) == {NOISE, CHEM}


def test_factors_for_hazards_ignores_unmapped():
    assert factors_for_hazards({"zzz"}, CATALOG) == set()
    assert factors_for_hazards(set(), CATALOG) == set()


def test_required_exams_union_with_strictest_periodicity():
    # PERIODIC appears in NOISE(12) and CHEM(24) → strictest 12; FLUOROGRAPHY from CHEM(24).
    result = required_exams_from_factors({NOISE, CHEM})
    assert result == {K.PERIODIC: 12, K.FLUOROGRAPHY: 24}


def test_worst_status_priority():
    assert worst_status(["ok", "due_soon", "overdue"]) == "overdue"
    assert worst_status(["ok", "missing", "due_soon"]) == "missing"
    assert worst_status(["ok"]) == "ok"
    assert worst_status([]) == "ok"
