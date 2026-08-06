"""Тесты чистой проекции декларации (без БД)."""

from types import SimpleNamespace

from app.services.sout_declaration import build_declaration_projection


def _wp(code="РМ-01", cls="acceptable", person_id=None):
    return SimpleNamespace(
        id=code,
        workplace_code=code,
        position_name="Слесарь",
        assessed_class=cls,
        person_id=person_id,
    )


def _factor(cls="acceptable"):
    return SimpleNamespace(code=None, name="x", measured_class=cls)


def test_projection_marks_eligible_and_ineligible() -> None:
    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="СОУТ", report_number="N1", report_date=None),
        workplaces_with_factors=[
            (_wp(code="РМ-01", cls="acceptable", person_id="p1"), []),
            (_wp(code="РМ-02", cls="harmful_3_1"), [_factor("harmful_3_1")]),
            (_wp(code="РМ-03", cls="acceptable"), [_factor("harmful_3_2")]),
        ],
    )
    by_code = {r.workplace_code: r for r in rows}
    assert by_code["РМ-01"].eligible is True
    assert by_code["РМ-01"].headcount == "1"  # person_id задан
    assert by_code["РМ-02"].eligible is False  # класс 3.1
    assert by_code["РМ-03"].eligible is False  # класс 2, но фактор 3.1
    assert by_code["РМ-03"].headcount == "—"  # person_id нет


def test_projection_report_ref_built_from_campaign() -> None:
    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="СОУТ", report_number="N1", report_date="2026-06-01"),
        workplaces_with_factors=[(_wp(), [])],
    )
    assert rows[0].report_ref == "N1 от 2026-06-01"


def test_projection_coerces_enum_class_value() -> None:
    enum_like = SimpleNamespace(value="optimal")
    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="x", report_number=None, report_date=None),
        workplaces_with_factors=[(_wp(cls=enum_like), [])],
    )
    assert rows[0].assessed_class == "optimal"
    assert rows[0].eligible is True


def test_declaration_schema_validates_from_dataclass() -> None:
    from app.schemas.sout import DeclarationRowRead

    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="x", report_number=None, report_date=None),
        workplaces_with_factors=[(_wp(person_id="p1"), [])],
    )
    read = DeclarationRowRead.model_validate(rows[0], from_attributes=True)
    assert read.workplace_code == "РМ-01"
    assert read.eligible is True
    assert read.headcount == "1"
