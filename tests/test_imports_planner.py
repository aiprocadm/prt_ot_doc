"""OPS-71 срез-1 (разд. 71.1): маппинг, валидация и план импорта.

Чистый домен, без БД. Что закрепляется:

* автоопределение колонок по заголовкам живого файла («Табельный №», «ФАМИЛИЯ»)
  и приоритет ручного переопределения над ним;
* отсутствие обязательной колонки — отказ по ФАЙЛУ, а не тысяча одинаковых
  построчных ошибок;
* **строка без естественного ключа отвергается** — повторный импорт такого файла
  тихо наплодил бы дубли, а идемпотентность требуется разд. 71.1 прямо;
* дубль внутри файла виден с номером строки-оригинала;
* незнакомое значение справочника — ошибка строки И сводка «чего не хватает»,
  а не молчаливый пропуск (разд. 71.3);
* повторный прогон того же файла даёт `skip` по всем строкам — это и есть
  идемпотентность;
* у обновления сохраняется снимок ПРЕЖНИХ значений: без него откат партии
  нечем исполнить.
"""

from __future__ import annotations

from datetime import date

from app.modules.imports.parsers import ParsedFile
from app.modules.imports.planner import (
    build_mapping,
    build_plan,
    make_key,
    normalize_header,
    resolve_rows,
    template_headers,
)
from app.modules.imports.registry import PERSONS_TARGET, POSITIONS_TARGET

LOOKUPS = {"company": {"акме": "co-1"}, "position": {"co-1\x1fслесарь": "pos-1"}}


def _parsed(rows: list[dict[str, object]]) -> ParsedFile:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return ParsedFile(headers=headers, rows=rows)


def _person_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Организация": "АКМЕ",
        "Фамилия": "Иванов",
        "Имя": "Иван",
        "Табельный номер": "001",
    }
    row.update(overrides)
    return row


class TestMapping:
    def test_headers_match_regardless_of_case_and_punctuation(self) -> None:
        result = build_mapping(PERSONS_TARGET, ["ТАБЕЛЬНЫЙ  №", "фамилия", "Имя", "Организация"])

        assert result.mapping["last_name"] == "фамилия"
        assert result.mapping["company_id"] == "Организация"
        assert result.missing_required == []

    def test_manual_override_wins_over_autodetection(self) -> None:
        headers = ["Организация", "Фамилия", "Имя", "Прозвище"]

        result = build_mapping(PERSONS_TARGET, headers, overrides={"middle_name": "Прозвище"})

        assert result.mapping["middle_name"] == "Прозвище"
        assert "Прозвище" not in result.unmapped_headers

    def test_unknown_headers_are_reported_not_silently_dropped(self) -> None:
        result = build_mapping(PERSONS_TARGET, ["Организация", "Фамилия", "Имя", "Оклад"])

        assert result.unmapped_headers == ["Оклад"]

    def test_missing_required_column_is_named(self) -> None:
        result = build_mapping(PERSONS_TARGET, ["Организация", "Имя"])

        assert "Фамилия" in result.missing_required

    def test_template_headers_are_what_autodetection_understands(self) -> None:
        headers = [h.rstrip(" *") for h in template_headers(PERSONS_TARGET)]

        result = build_mapping(PERSONS_TARGET, headers)

        assert result.missing_required == []
        assert result.unmapped_headers == []


class TestResolve:
    def test_lookup_resolves_and_raw_position_text_is_kept(self) -> None:
        parsed = _parsed([_person_row(**{"Должность": "Слесарь"})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, unknown = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].ok, rows[0].errors
        assert rows[0].values["company_id"] == "co-1"
        assert rows[0].values["position_id"] == "pos-1"
        # Свободнотекстовая должность не теряется при сопоставлении со справочником.
        assert rows[0].values["position_title"] == "Слесарь"
        assert unknown == {}

    def test_unknown_reference_is_an_error_and_a_summary(self) -> None:
        parsed = _parsed([_person_row(**{"Должность": "Космонавт"})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, unknown = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert [e.code for e in rows[0].errors] == ["unknown_reference"]
        assert unknown == {"position": ["Космонавт"]}

    def test_dates_accept_both_russian_and_iso_notation(self) -> None:
        parsed = _parsed(
            [
                _person_row(**{"Дата рождения": "05.03.1980"}),
                _person_row(**{"Табельный номер": "002", "Дата рождения": "1980-03-05"}),
            ]
        )
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].values["birth_date"] == date(1980, 3, 5)
        assert rows[1].values["birth_date"] == date(1980, 3, 5)

    def test_broken_date_names_the_column(self) -> None:
        parsed = _parsed([_person_row(**{"Дата рождения": "вчера"})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].errors[0].code == "invalid_value"
        assert "Дата рождения" in rows[0].errors[0].message

    def test_excel_numeric_personnel_number_does_not_become_a_new_key(self) -> None:
        """XLSX отдаёт табельный как 1001.0 — как строка это уже другой ключ."""

        parsed = _parsed([_person_row(**{"Табельный номер": 1001.0})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].values["personnel_number"] == "1001"

    def test_russian_status_words_are_understood(self) -> None:
        parsed = _parsed([_person_row(**{"Статус": "Уволен"})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].values["employment_status"] == "terminated"

    def test_row_without_any_key_is_refused(self) -> None:
        parsed = _parsed([{"Организация": "АКМЕ", "Фамилия": "Иванов", "Имя": "Иван"}])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert [e.code for e in rows[0].errors] == ["no_natural_key"]

    def test_fio_and_birth_date_serve_as_the_fallback_key(self) -> None:
        parsed = _parsed(
            [
                {
                    "Организация": "АКМЕ",
                    "Фамилия": "Иванов",
                    "Имя": "Иван",
                    "Дата рождения": "05.03.1980",
                }
            ]
        )
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].ok, rows[0].errors
        assert rows[0].key_title == "организация + ФИО + дата рождения"

    def test_duplicate_inside_the_file_points_at_the_original_row(self) -> None:
        parsed = _parsed([_person_row(), _person_row(**{"Имя": "Пётр"})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].ok
        assert rows[1].errors[0].code == "duplicate_in_file"
        assert "2" in rows[1].errors[0].message

    def test_missing_required_value_names_the_column(self) -> None:
        parsed = _parsed([_person_row(**{"Фамилия": ""})])
        mapping = build_mapping(PERSONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(PERSONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].errors[0].code == "required"
        assert "Фамилия" in rows[0].errors[0].message


class TestPlan:
    def _plan(self, rows_payload, existing):
        parsed = _parsed(rows_payload)
        mapping = build_mapping(PERSONS_TARGET, parsed.headers)
        resolved, unknown = resolve_rows(PERSONS_TARGET, parsed, mapping.mapping, LOOKUPS)
        return build_plan(
            PERSONS_TARGET,
            resolved,
            existing,
            mapping.mapping,
            mapping.unmapped_headers,
            unknown,
        )

    def _existing_key(self, values: dict[str, object]) -> str:
        return "организация + табельный номер\x1f" + make_key(
            ("company_id", "personnel_number"), values
        )

    def test_new_row_is_planned_as_create(self) -> None:
        plan = self._plan([_person_row()], {})

        assert plan.counts()["create"] == 1

    def test_identical_reimport_is_skipped_not_duplicated(self) -> None:
        current = {
            "id": "p-1",
            "company_id": "co-1",
            "personnel_number": "001",
            "last_name": "Иванов",
            "first_name": "Иван",
        }

        plan = self._plan([_person_row()], {self._existing_key(current): current})

        assert plan.counts()["skip"] == 1
        assert plan.counts()["update"] == 0

    def test_changed_field_yields_update_with_a_before_snapshot(self) -> None:
        current = {
            "id": "p-1",
            "company_id": "co-1",
            "personnel_number": "001",
            "last_name": "Иванов",
            "first_name": "Пётр",
        }

        plan = self._plan([_person_row()], {self._existing_key(current): current})
        row = plan.rows[0]

        assert row.action == "update"
        assert row.values == {"first_name": "Иван"}
        # Без снимка прежнего значения откат партии нечем исполнить.
        assert row.before == {"first_name": "Пётр"}
        assert row.entity_id == "p-1"

    def test_error_rows_do_not_block_the_correct_ones(self) -> None:
        """Частичный импорт из разд. 71.1: файл не падает целиком."""

        plan = self._plan(
            [_person_row(), _person_row(**{"Табельный номер": "002", "Фамилия": ""})],
            {},
        )

        counts = plan.counts()
        assert counts["create"] == 1
        assert counts["error"] == 1


class TestPositionsTarget:
    def test_position_key_is_company_plus_name(self) -> None:
        parsed = _parsed([{"Организация": "АКМЕ", "Должность": "Слесарь"}])
        mapping = build_mapping(POSITIONS_TARGET, parsed.headers).mapping

        rows, _ = resolve_rows(POSITIONS_TARGET, parsed, mapping, LOOKUPS)

        assert rows[0].ok, rows[0].errors
        assert rows[0].key_title == "организация + должность"


def test_normalize_header_folds_yo_and_number_sign() -> None:
    assert normalize_header("Дата приёма") == normalize_header("дата приема")
    # «№» — общепринятое сокращение слова «номер», и заголовок с ним обязан
    # попадать в тот же синоним, что и полное слово.
    assert normalize_header("Табельный №") == normalize_header("Табельный номер")


def test_personnel_number_column_matches_the_number_sign_header() -> None:
    result = build_mapping(PERSONS_TARGET, ["Организация", "Фамилия", "Имя", "Табельный №"])

    assert result.mapping["personnel_number"] == "Табельный №"
    assert result.unmapped_headers == []
