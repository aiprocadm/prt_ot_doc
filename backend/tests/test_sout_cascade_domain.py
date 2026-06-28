"""Юниты чистого домена каскада СОУТ (без БД, без async) + схемы."""
from app.schemas.sout import CascadeMedicalAction, CascadePreview, CascadeResult


def test_cascade_schema_roundtrip():
    action = CascadeMedicalAction(
        exam_kind="periodic", op="create", periodicity_months=12,
        interval_days=365, target_class="harmful_3_1", current_class=None,
        factor_codes=["4.1"], reason="x",
    )
    preview = CascadePreview(
        assessed_class="harmful_3_1", can_apply=True, medical=[action], ppe_advisory=[],
    )
    assert preview.medical[0].op == "create"
    assert preview.can_apply is True
    result = CascadeResult(created=1, reclassified=0, conflicts=0, ppe_advisory_count=2)
    assert result.created == 1
