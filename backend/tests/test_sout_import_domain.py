"""Юниты чистого домена импорта СОУТ (без БД, без async)."""
import pytest

from app.domains.sout.import_report import (
    DiffRow,
    ParsedFactor,
    ParsedWorkplace,
    UnsupportedImportFormat,
    diff_campaign,
    parse_class_label,
    parse_report,
    validate_parsed,
)


def test_parse_class_label_digits_enum_ru():
    assert parse_class_label("3.1") == ("harmful_3_1", None)
    assert parse_class_label("2") == ("acceptable", None)
    assert parse_class_label("optimal") == ("optimal", None)
    assert parse_class_label("Допустимый") == ("acceptable", None)
    assert parse_class_label("класс 3.2") == ("harmful_3_2", None)
    assert parse_class_label("вредный 3.4") == ("harmful_3_4", None)


def test_parse_class_label_blank_and_garbage():
    assert parse_class_label(None) == (None, None)
    assert parse_class_label("   ") == (None, None)
    assert parse_class_label("абракадабра") == (None, "абракадабра")


def _wp(code="РМ-01", pos="Слесарь", cls="acceptable", factors=None, conflict=False):
    return ParsedWorkplace(
        workplace_code=code, position_name=pos, assessed_class=cls,
        class_unparsed=None, factors=factors or [], conflict=conflict,
    )


def test_validate_blocking_rules():
    rows = [
        _wp(code="", pos="X"),                       # пустой код
        _wp(code="РМ-2", pos=""),                     # пустая должность
        ParsedWorkplace("РМ-3", "X", None, "мусор", []),  # класс не распознан
        _wp(code="РМ-4", conflict=True),             # конфликт атрибутов
    ]
    issues = validate_parsed(rows)
    assert issues[0].errors and issues[1].errors and issues[2].errors and issues[3].errors


def test_validate_warning_class_2_with_harmful_factor():
    wp = _wp(cls="acceptable", factors=[ParsedFactor(None, "Шум", "harmful_3_1", None)])
    issues = validate_parsed([wp])
    assert issues[0].errors == []
    assert any("вредный фактор" in w for w in issues[0].warnings)


def test_validate_warning_unparsed_factor_class():
    wp = _wp(factors=[ParsedFactor(None, "Вибрация", None, "???")])
    issues = validate_parsed([wp])
    assert any("фактор" in w for w in issues[0].warnings)


def test_diff_campaign_classifies():
    parsed = [_wp(code="РМ-1", cls="acceptable"), _wp(code="РМ-2", cls="harmful_3_1"), _wp(code="РМ-3", cls="optimal")]
    existing = [("РМ-1", "acceptable"), ("РМ-2", "optimal"), ("РМ-9", "acceptable")]
    by_code = {d.workplace_code: d for d in diff_campaign(parsed, existing)}
    assert by_code["РМ-1"].change == "unchanged"
    assert by_code["РМ-2"].change == "changed"
    assert by_code["РМ-3"].change == "new"
    assert by_code["РМ-9"].change == "removed"


def test_parse_report_rejects_unknown_extension():
    with pytest.raises(UnsupportedImportFormat):
        parse_report(b"x", "report.pdf")


def test_validate_no_error_when_class_blank_on_overall_workplace():
    # РМ без класса вовсе — допустимо, не блокирующая ошибка
    wp = ParsedWorkplace("РМ-7", "Слесарь", None, None, [])
    issues = validate_parsed([wp])
    assert issues[0].errors == []
