"""Тесты сервиса импорта СОУТ + схем (часть без БД)."""


def test_import_preview_schema_roundtrip():
    from app.schemas.sout import ImportFactorRow, ImportPreview, ImportWorkplaceRow

    row = ImportWorkplaceRow(
        row_index=0, workplace_code="РМ-01", position_name="Слесарь",
        parsed_class="acceptable", current_class=None, change="new",
        factors=[ImportFactorRow(code=None, name="Шум", parsed_class="harmful_3_1", class_unparsed=None)],
        errors=[], warnings=["класс 1-2, но указан вредный фактор (3.1+)"],
    )
    preview = ImportPreview(
        campaign_id="c1", rows=[row], new_count=1, changed_count=0,
        unchanged_count=0, removed_count=0, error_count=0, can_apply=True,
    )
    assert preview.rows[0].change == "new"
    assert preview.can_apply is True
