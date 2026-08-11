"""Юниты чистого домена импорта СОУТ (без БД, без async)."""

from io import BytesIO

import pytest

from app.domains.sout.import_report import (
    ParsedFactor,
    ParsedWorkplace,
    UnsupportedImportFormat,
    diff_campaign,
    parse_class_label,
    parse_csv,
    parse_fgis_xml,
    parse_report,
    parse_xlsx,
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
        workplace_code=code,
        position_name=pos,
        assessed_class=cls,
        class_unparsed=None,
        factors=factors or [],
        conflict=conflict,
    )


def test_validate_blocking_rules():
    rows = [
        _wp(code="", pos="X"),  # пустой код
        _wp(code="РМ-2", pos=""),  # пустая должность
        ParsedWorkplace("РМ-3", "X", None, "мусор", []),  # класс не распознан
        _wp(code="РМ-4", conflict=True),  # конфликт атрибутов
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
    parsed = [
        _wp(code="РМ-1", cls="acceptable"),
        _wp(code="РМ-2", cls="harmful_3_1"),
        _wp(code="РМ-3", cls="optimal"),
    ]
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


def test_parse_csv_groups_factors_by_code():
    csv_text = (
        "workplace_code,position_name,assessed_class,factor_name,factor_class\n"
        "РМ-01,Слесарь,3.1,Шум,3.1\n"
        "РМ-01,Слесарь,3.1,Вибрация,2\n"
        "РМ-02,Сварщик,2,,\n"
    ).encode("utf-8")
    wps = parse_csv(csv_text)
    assert [w.workplace_code for w in wps] == ["РМ-01", "РМ-02"]
    assert wps[0].assessed_class == "harmful_3_1"
    assert [f.name for f in wps[0].factors] == ["Шум", "Вибрация"]
    assert wps[0].factors[0].measured_class == "harmful_3_1"
    assert wps[1].factors == []


def test_parse_csv_detects_conflict_on_repeated_code():
    csv_text = (
        "workplace_code,position_name,assessed_class\n"
        "РМ-01,Слесарь,2\n"
        "РМ-01,Слесарь,3.1\n"  # тот же код, другой класс → конфликт
    ).encode("utf-8")
    wps = parse_csv(csv_text)
    assert wps[0].conflict is True


def test_parse_csv_russian_headers():
    csv_text = ("Код РМ,Должность,Класс\n" "РМ-05,Оператор,допустимый\n").encode("utf-8")
    wps = parse_csv(csv_text)
    assert wps[0].workplace_code == "РМ-05"
    assert wps[0].position_name == "Оператор"
    assert wps[0].assessed_class == "acceptable"


def test_parse_xlsx_roundtrip():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["workplace_code", "position_name", "assessed_class", "factor_name", "factor_class"])
    ws.append(["РМ-01", "Слесарь", "3.1", "Шум", "3.1"])
    buf = BytesIO()
    wb.save(buf)
    wps = parse_xlsx(buf.getvalue())
    assert wps[0].workplace_code == "РМ-01"
    assert wps[0].assessed_class == "harmful_3_1"
    assert wps[0].factors[0].name == "Шум"


def test_parse_fgis_xml_subset():
    xml = (
        "<sout><workplace code='РМ-01' position='Слесарь'>"
        "<assessed_class>acceptable</assessed_class>"
        "<factors><factor code='4.50' name='Шум' class='harmful_3_1'/>"
        "<factor name='Вибрация' class='2'/></factors>"
        "</workplace></sout>"
    ).encode("utf-8")
    wps = parse_fgis_xml(xml)
    assert wps[0].workplace_code == "РМ-01"
    assert wps[0].position_name == "Слесарь"
    assert wps[0].assessed_class == "acceptable"
    assert [f.name for f in wps[0].factors] == ["Шум", "Вибрация"]
    assert wps[0].factors[0].measured_class == "harmful_3_1"
