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
        "periodic",
        "preliminary",
        "psychiatric",
        "fluorography",
        "health_book",
    }
    assert MedicalFitness.UNFIT.value == "unfit"
    assert {f.value for f in MedicalFitness} == {"fit", "fit_with_restrictions", "unfit"}
    assert {s.value for s in MedicalReferralStatus} == {
        "issued",
        "scheduled",
        "completed",
        "cancelled",
    }
    assert {s.value for s in MedicalSuspensionStatus} == {"active", "lifted"}
    assert {r.value for r in MedicalSuspensionReason} == {"unfit", "contraindication"}


def test_medical_exam_has_new_columns():
    from app.models.models import MedicalExam

    cols = {c.name for c in MedicalExam.__table__.columns}
    assert {
        "exam_kind",
        "fitness",
        "restrictions",
        "contraindications",
        "referral_id",
        "medical_org_name",
    }.issubset(cols)


def test_new_medical_tables_exist():
    from app.models.models import MedicalNorm, MedicalReferral, MedicalSuspension

    assert MedicalNorm.__tablename__ == "medical_norm"
    assert MedicalReferral.__tablename__ == "medical_referral"
    assert MedicalSuspension.__tablename__ == "medical_suspension"
    norm_cols = {c.name for c in MedicalNorm.__table__.columns}
    assert {
        "position_id",
        "hazard_id",
        "exam_kind",
        "interval_days",
        "working_conditions_class",
    }.issubset(norm_cols)
    ref_cols = {c.name for c in MedicalReferral.__table__.columns}
    assert {
        "person_id",
        "exam_kind",
        "due_at",
        "status",
        "medical_org_name",
        "issued_by",
        "result_exam_id",
    }.issubset(ref_cols)
    susp_cols = {c.name for c in MedicalSuspension.__table__.columns}
    assert {
        "person_id",
        "reason",
        "source_exam_id",
        "started_at",
        "lifted_at",
        "status",
        "lifted_by",
    }.issubset(susp_cols)
