"""Юниты чистого домена каскада СОУТ (без БД, без async) + схемы."""
from types import SimpleNamespace

from app.domains.sout.cascade import build_cascade_plan, months_to_interval_days
from app.models.models import MedicalExamKind
from app.models.sout import SoutClass
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


def test_months_to_interval_days():
    assert months_to_interval_days(12) == 365   # совпадает с DEFAULT_INTERVAL_DAYS[PERIODIC]
    assert months_to_interval_days(60) == 1825  # PSYCHIATRIC


# Каталог 29н: фактор "4.1" требует periodic каждые 12 мес.
_CATALOG = [("4.1", "Шум", (MedicalExamKind.PERIODIC,), 12)]


def _factor(hid="h1"):
    return SimpleNamespace(hazard_id=hid, name="Шум", code="4.1", measured_class=SoutClass.HARMFUL_3_1)


def test_plan_create_when_no_norm():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={}, existing_ppe_pairs=set(),
    )
    assert [a.op for a in plan.medical] == ["create"]
    assert plan.medical[0].exam_kind == "periodic"
    assert plan.medical[0].interval_days == 365
    assert plan.medical[0].target_class == "harmful_3_1"


def test_plan_reclass_when_class_empty():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={"periodic": None}, existing_ppe_pairs=set(),
    )
    assert [a.op for a in plan.medical] == ["reclass"]


def test_plan_conflict_when_class_differs_nonempty():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={"periodic": "acceptable"}, existing_ppe_pairs=set(),
    )
    assert [a.op for a in plan.medical] == ["conflict"]
    assert plan.medical[0].current_class == "acceptable"


def test_plan_idempotent_when_class_matches():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={"periodic": "harmful_3_1"}, existing_ppe_pairs=set(),
    )
    assert plan.medical == []


def test_plan_empty_when_class_none():
    plan = build_cascade_plan(
        assessed_class=None, position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={}, existing_ppe_pairs=set(),
    )
    assert plan.medical == []


def test_plan_ppe_advisory_from_factors():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={}, existing_ppe_pairs=set(),
    )
    assert [a.hazard_id for a in plan.ppe_advisory] == ["h1"]
