"""Pure read-projection engine for СОУТ norm suggestions (срез-3, P10-04).

No DB access — callers pass already-loaded rows (or SimpleNamespace in tests).
СИЗ side dedups by ``(position_id, hazard_id)`` presence in existing PPENorm;
medical side reuses the 29н engine and dedups by ``(position_id, exam_kind)``.
Nothing here mutates target tables — confirmation goes through the targets' own
write endpoints (e.g. ``POST /ppe/norms``).
"""
from __future__ import annotations

from typing import Iterable

from app.domains.medical import lifecycle as med_lc
from app.schemas.sout import MedicalExamSuggestion, PpeNormSuggestion


def build_ppe_norm_suggestions(
    *,
    position_id: str | None,
    factors: Iterable,
    hazard_titles: dict[str, str],
    existing_norm_pairs: set[tuple[str, str]],
) -> list[PpeNormSuggestion]:
    """Propose a PPE norm per linked (position, hazard) pair lacking any norm.

    ``factors`` are SoutFactor rows (each exposes ``hazard_id``/``name``/``code``/
    ``measured_class``). A pair already covered by an existing PPENorm (present in
    ``existing_norm_pairs``) is skipped — item_name is not guessed, so the signal is
    simply "this harmful factor has no PPE norm yet". Multiple factors on the same
    hazard collapse to one suggestion.
    """
    if position_id is None:
        return []
    out: list[PpeNormSuggestion] = []
    seen: set[tuple[str, str]] = set()
    for f in factors:
        hid = getattr(f, "hazard_id", None)
        if hid is None:
            continue
        pair = (position_id, hid)
        if pair in existing_norm_pairs or pair in seen:
            continue
        seen.add(pair)
        cls = getattr(f, "measured_class", None)
        cls_label = cls.value if cls is not None else "—"
        out.append(
            PpeNormSuggestion(
                position_id=position_id,
                hazard_id=hid,
                hazard_title=hazard_titles.get(hid, ""),
                factor_name=getattr(f, "name", ""),
                factor_code=getattr(f, "code", None),
                measured_class=cls,
                reason=f"СОУТ: вредный фактор «{getattr(f, 'name', '')}» (класс {cls_label}) "
                f"без нормы СИЗ для должности",
            )
        )
    return out


def build_medical_exam_suggestions(
    *,
    position_id: str | None,
    hazard_factor_codes: set[str],
    factor_catalog: Iterable,
    existing_norm_kinds: set,
) -> list[MedicalExamSuggestion]:
    """Propose required medical exams derived from linked hazards' 29н factors.

    Reuses the medical engine: linked hazards carry ``medical_factor_code`` →
    ``factors_for_hazards`` filters the catalog → ``required_exams_from_factors``
    yields kind→strictest-periodicity. A kind already covered by an existing
    MedicalNorm for the position (``existing_norm_kinds``) is skipped.
    """
    if position_id is None:
        return []
    matched = med_lc.factors_for_hazards(set(hazard_factor_codes), factor_catalog)
    required = med_lc.required_exams_from_factors(matched)  # dict[MedicalExamKind, int]
    out: list[MedicalExamSuggestion] = []
    for kind, months in required.items():
        if kind in existing_norm_kinds:
            continue
        codes = sorted(
            code for (code, _name, kinds, _m) in matched if kind in kinds
        )
        out.append(
            MedicalExamSuggestion(
                position_id=position_id,
                exam_kind=kind.value,
                periodicity_months=int(months),
                factor_codes=codes,
                reason=f"СОУТ: факторы 29н {codes} требуют осмотр «{kind.value}» "
                f"каждые {int(months)} мес. — нормы нет",
            )
        )
    return out
