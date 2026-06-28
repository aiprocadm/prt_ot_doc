"""Чистый домен авто-каскада класса СОУТ → план изменений мед-норм (+ совет СИЗ).

Без БД/FastAPI. Caller передаёт уже загруженные строки. Медицинская часть
переиспользует 29н-движок (factors_for_hazards / required_exams_from_factors),
но НЕ пропускает существующие нормы — каскаду нужны все требуемые виды осмотров,
чтобы классифицировать каждое действие как create/reclass/conflict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.domains.medical import lifecycle as med_lc
from app.domains.sout.suggestions import build_ppe_norm_suggestions
from app.schemas.sout import PpeNormSuggestion

CascadeOp = Literal["create", "reclass", "conflict"]


@dataclass
class MedicalCascadeAction:
    exam_kind: str
    op: CascadeOp
    periodicity_months: int
    interval_days: int
    target_class: str
    current_class: str | None
    factor_codes: list[str]
    reason: str


@dataclass
class CascadePlan:
    assessed_class: str | None
    medical: list[MedicalCascadeAction] = field(default_factory=list)
    ppe_advisory: list[PpeNormSuggestion] = field(default_factory=list)


def months_to_interval_days(months: int) -> int:
    """29н периодичность (мес) → interval_days. 12→365, 60→1825 (как DEFAULT_INTERVAL_DAYS)."""
    return months * 365 // 12


def build_cascade_plan(
    *,
    assessed_class: str | None,
    position_id: str | None,
    factors: Iterable,
    hazard_meta: dict[str, tuple[str, str | None]],
    factor_catalog: Iterable,
    existing_med_norms: dict[str, str | None],
    existing_ppe_pairs: set[tuple[str, str]],
) -> CascadePlan:
    """Построить план каскада. ``existing_med_norms`` — {exam_kind_value: class|None}
    только для общих (hazard_id IS NULL) норм должности."""
    plan = CascadePlan(assessed_class=assessed_class)
    if assessed_class is None or position_id is None:
        return plan

    hazard_factor_codes = {meta[1] for meta in hazard_meta.values() if meta[1]}
    matched = med_lc.factors_for_hazards(hazard_factor_codes, factor_catalog)
    required = med_lc.required_exams_from_factors(matched)  # {MedicalExamKind: months}

    for kind, months in sorted(required.items(), key=lambda kv: kv[0].value):
        kv = kind.value
        codes = sorted(code for (code, _n, kinds, _m) in matched if kind in kinds)
        interval = months_to_interval_days(int(months))
        if kv not in existing_med_norms:
            op: CascadeOp = "create"
            current: str | None = None
            reason = f"СОУТ класс {assessed_class}: добавить норму осмотра «{kv}» ({int(months)} мес.)"
        else:
            current = existing_med_norms[kv]
            if current in (None, ""):
                op = "reclass"
                reason = f"СОУТ класс {assessed_class}: проставить класс в норме осмотра «{kv}»"
            elif current != assessed_class:
                op = "conflict"
                reason = (
                    f"Норма осмотра «{kv}» имеет класс {current} ≠ СОУТ {assessed_class} "
                    f"— проверьте вручную (apply не перезапишет)"
                )
            else:
                continue  # класс уже совпадает — действие не нужно
        plan.medical.append(
            MedicalCascadeAction(
                exam_kind=kv, op=op, periodicity_months=int(months),
                interval_days=interval, target_class=assessed_class,
                current_class=current, factor_codes=codes, reason=reason,
            )
        )

    hazard_titles = {hid: meta[0] for hid, meta in hazard_meta.items()}
    plan.ppe_advisory = build_ppe_norm_suggestions(
        position_id=position_id, factors=factors,
        hazard_titles=hazard_titles, existing_norm_pairs=existing_ppe_pairs,
    )
    return plan
