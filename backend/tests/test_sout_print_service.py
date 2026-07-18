"""Тесты сборки PrintData в sout_print (чистые части, без БД)."""
from types import SimpleNamespace

from app.services.sout_print import _card_print_data, _summary_print_data


def _wp(**over):
    base = dict(
        id="w1", workplace_code="РМ-01", position_name="Сварщик",
        assessed_class="harmful_3_2", assessment_date=None, next_assessment_date=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _factor(name="Шум", code="4.50", cls="harmful_3_1"):
    return SimpleNamespace(code=code, name=name, measured_class=cls)


def _guarantee(kind="milk", detail=None):
    return SimpleNamespace(kind=kind, detail=detail)


def test_card_print_data_maps_rows() -> None:
    data = _card_print_data(
        org_header="ООО Ромашка",
        generated_at="2026-06-27",
        campaign=SimpleNamespace(expert_org_name="Эксп", report_number="N1", report_date=None),
        workplace=_wp(),
        factors=[_factor()],
        guarantees=[_guarantee()],
    )
    assert data.workplace_code == "РМ-01"
    assert data.expert_org_name == "Эксп"
    assert data.assessed_class == "harmful_3_2"
    assert len(data.factors) == 1 and data.factors[0].name == "Шум"
    assert data.guarantees[0].kind == "milk"


def test_summary_print_data_counts_harmful_and_classes() -> None:
    data = _summary_print_data(
        org_header="ООО Ромашка",
        generated_at="2026-06-27",
        campaign=SimpleNamespace(name="СОУТ 2026", expert_org_name=None, report_number=None, report_date=None),
        workplaces_with_factors=[
            (_wp(workplace_code="РМ-01", assessed_class="harmful_3_2"),
             [_factor(cls="harmful_3_1"), _factor(cls="acceptable")]),
            (_wp(workplace_code="РМ-02", assessed_class="acceptable"), []),
        ],
    )
    assert [r.workplace_code for r in data.rows] == ["РМ-01", "РМ-02"]
    assert data.rows[0].harmful_factor_count == 1   # один фактор 3.1
    assert dict(data.class_counts)["3.2"] == 1
    assert dict(data.class_counts)["2 (допустимый)"] == 1


def test_class_enums_coerced_to_raw_value() -> None:
    # measured_class может прийти как enum-объект с .value — сборка берёт .value/str
    enum_like = SimpleNamespace(value="dangerous")
    data = _card_print_data(
        org_header="o", generated_at=None,
        campaign=SimpleNamespace(expert_org_name=None, report_number=None, report_date=None),
        workplace=_wp(assessed_class=enum_like),
        factors=[], guarantees=[],
    )
    assert data.assessed_class == "dangerous"
