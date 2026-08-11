"""Тесты печатного бланка наряда-допуска: колонка «Группа» для электро (903н).

Покрываем:
- электро (show_member_groups=True) → таблица 3 колонки, шапка «Группа», значение «IV»
- не-электро (show_member_groups=False) → таблица 2 колонки, «Группа» в шапке НЕТ
"""

from __future__ import annotations

from io import BytesIO

from docx import Document

from app.domains.work_permits.print_form import (
    WorkPermitPrintData,
    build_work_permit_docx,
)


def _minimal_data(**kwargs) -> WorkPermitPrintData:
    """Минимальный снимок наряда для юнит-теста печати."""
    defaults = dict(
        number="WP-001",
        work_type_label="Электроустановки",
        legal_reference="903н",
        status_label="Выдан",
        org_header="ООО Тест",
        subdivision=None,
        planned_start=None,
        planned_end=None,
        zone_text="Трансформаторная будка",
        content_text=None,
        conditions_text=None,
        equipment_text=None,
        hazards_text=None,
        structured_section=None,
        measures_before=None,
        measures_during=None,
        special_conditions=None,
        ppe_text=None,
        members=[],
        briefing=None,
        daily_admissions=[],
        extensions=[],
        completion=None,
        closed_at=None,
        signatures=[],
    )
    defaults.update(kwargs)
    return WorkPermitPrintData(**defaults)


def _get_member_table(doc: Document):
    """Ищем таблицу «Ответственные лица и состав бригады» по первой ячейке шапки."""
    for tbl in doc.tables:
        hdr_cells = [c.text for c in tbl.rows[0].cells]
        if hdr_cells and hdr_cells[0] == "Роль":
            return tbl
    return None


def _parse_docx(docx_bytes: bytes) -> Document:
    return Document(BytesIO(docx_bytes))


class TestElectricalMemberGroupColumn:
    """Электро-наряд: 3 колонки + шапка «Группа» + значение группы."""

    def test_header_has_group_column(self):
        data = _minimal_data(
            members=[("Член бригады", "Иванов И.И.", "IV")],
            show_member_groups=True,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None, "Таблица бригады не найдена"
        hdr = [c.text for c in tbl.rows[0].cells]
        assert "Группа" in hdr, f"Шапка не содержит 'Группа': {hdr}"

    def test_table_has_3_columns(self):
        data = _minimal_data(
            members=[("Член бригады", "Иванов И.И.", "IV")],
            show_member_groups=True,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        assert len(tbl.columns) == 3, f"Ожидалось 3 колонки, получено {len(tbl.columns)}"

    def test_member_row_contains_group_value(self):
        data = _minimal_data(
            members=[("Член бригады", "Иванов И.И.", "IV")],
            show_member_groups=True,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        row_texts = [c.text for c in tbl.rows[1].cells]
        assert "IV" in row_texts, f"Значение 'IV' не найдено в строке: {row_texts}"

    def test_none_group_renders_dash(self):
        """Если группа не определена — отображается «—»."""
        data = _minimal_data(
            members=[("Наблюдающий", "Петров П.П.", None)],
            show_member_groups=True,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        row_texts = [c.text for c in tbl.rows[1].cells]
        assert "—" in row_texts, f"Ожидался '—' для None-группы, строка: {row_texts}"

    def test_multiple_members_all_have_groups(self):
        members = [
            ("Выдающий наряд", "Сидоров С.С.", "IV"),
            ("Производитель работ", "Козлов К.К.", "III"),
            ("Член бригады", "Новиков Н.Н.", None),
        ]
        data = _minimal_data(members=members, show_member_groups=True)
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        # Строки 1,2,3 (0 — шапка)
        assert tbl.rows[1].cells[2].text == "IV"
        assert tbl.rows[2].cells[2].text == "III"
        assert tbl.rows[3].cells[2].text == "—"

    def test_docx_bytes_contain_group_text(self):
        """Интеграционная проверка: строка «Группа» и «IV» есть в DOCX-байтах текста."""
        data = _minimal_data(
            members=[("Член бригады", "Иванов И.И.", "IV")],
            show_member_groups=True,
        )
        docx_bytes = build_work_permit_docx(data)
        doc = _parse_docx(docx_bytes)
        all_text = "\n".join(
            cell.text for tbl in doc.tables for row in tbl.rows for cell in row.cells
        )
        assert "Группа" in all_text
        assert "IV" in all_text


class TestNonElectricalNoGroupColumn:
    """Не-электро наряд: 2 колонки, «Группа» в шапке НЕТ."""

    def test_header_has_no_group_column(self):
        data = _minimal_data(
            work_type_label="Огневые работы",
            legal_reference="1479н",
            members=[("Член бригады", "Иванов И.И.", None)],
            show_member_groups=False,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        hdr = [c.text for c in tbl.rows[0].cells]
        assert "Группа" not in hdr, f"Шапка не должна содержать 'Группа' для не-электро: {hdr}"

    def test_table_has_2_columns(self):
        data = _minimal_data(
            work_type_label="Огневые работы",
            legal_reference="1479н",
            members=[("Член бригады", "Иванов И.И.", None)],
            show_member_groups=False,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        assert len(tbl.columns) == 2, f"Ожидалось 2 колонки, получено {len(tbl.columns)}"

    def test_default_show_member_groups_is_false(self):
        """По умолчанию show_member_groups=False — обратная совместимость."""
        data = _minimal_data(
            members=[("Член бригады", "Иванов И.И.", None)],
        )
        # show_member_groups не передаётся явно → default False
        assert data.show_member_groups is False

    def test_old_2tuple_members_still_work_without_show_groups(self):
        """members как тройки c None-группой при show_member_groups=False — 2 колонки."""
        data = _minimal_data(
            members=[("Член бригады", "Иванов И.И.", None)],
            show_member_groups=False,
        )
        doc = _parse_docx(build_work_permit_docx(data))
        tbl = _get_member_table(doc)
        assert tbl is not None
        assert len(tbl.columns) == 2
        # Значение фио попадает во вторую колонку
        assert tbl.rows[1].cells[1].text == "Иванов И.И."
