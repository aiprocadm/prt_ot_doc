from __future__ import annotations

from app.models.models import (
    MedicalExamKind,
    MedicalFitness,
    MedicalReferralStatus,
    MedicalSuspensionReason,
    MedicalSuspensionStatus,
)


def test_medical_enum_values_are_lowercase():
    assert MedicalExamKind.PERIODIC.value == "periodic"
    assert {k.value for k in MedicalExamKind} == {
        "periodic", "preliminary", "psychiatric", "fluorography", "health_book",
    }
    assert MedicalFitness.UNFIT.value == "unfit"
    assert {f.value for f in MedicalFitness} == {"fit", "fit_with_restrictions", "unfit"}
    assert {s.value for s in MedicalReferralStatus} == {
        "issued", "scheduled", "completed", "cancelled",
    }
    assert {s.value for s in MedicalSuspensionStatus} == {"active", "lifted"}
    assert {r.value for r in MedicalSuspensionReason} == {"unfit", "contraindication"}
