"""BIZ-50 срез-1 — правила готовности комплекта (разд. 50.2, шаг 3). Без БД."""

from __future__ import annotations

from app.domains.packs.readiness import PROBLEM_ROWS_LIMIT, analyze_pack_readiness


def _codes(readiness) -> set[str]:
    return {problem.code for problem in readiness.problems}


def _by_code(readiness, code):
    return next(problem for problem in readiness.problems if problem.code == code)


def test_complete_source_is_ready() -> None:
    readiness = analyze_pack_readiness(
        mapping={"fio": "фио", "position": "должность"},
        columns=["фио", "должность"],
        rows=[{"фио": "Иванов", "должность": "Слесарь"}],
        selected_rows=[],
        documents_per_row=3,
        preset_active=True,
    )
    assert readiness.ready is True
    assert readiness.score == 100
    # Три документа на одну строку — столько и обещаем.
    assert readiness.documents_total == 3
    assert readiness.problems == ()


def test_all_missing_columns_are_listed_at_once() -> None:
    """Пять пропущенных колонок чинились пятью прогонами — теперь одним."""

    readiness = analyze_pack_readiness(
        mapping={"a": "нет1", "b": "нет2", "c": "есть"},
        columns=["есть"],
        rows=[{"есть": "x"}],
        selected_rows=[],
        documents_per_row=1,
        preset_active=True,
    )
    assert readiness.ready is False
    problem = _by_code(readiness, "SOURCE_COLUMN_MISSING")
    assert problem.blocking is True
    assert "нет1" in problem.message and "нет2" in problem.message
    # Блокирующая проблема — обещать документы нельзя.
    assert readiness.documents_total == 0
    assert readiness.score == 0


def test_empty_value_warns_but_does_not_block() -> None:
    """Пусто в строке — документ выйдет с пробелом, но выйдет."""

    readiness = analyze_pack_readiness(
        mapping={"fio": "фио"},
        columns=["фио"],
        rows=[{"фио": "Иванов"}, {"фио": "   "}, {"фио": None}],
        selected_rows=[],
        documents_per_row=2,
        preset_active=True,
    )
    assert readiness.ready is True
    problem = _by_code(readiness, "VALUE_EMPTY")
    assert problem.blocking is False
    assert problem.rows == (2, 3)
    assert readiness.rows_ready == 1
    assert readiness.score == 33
    # Документы всё равно будут — с дырой, но будут.
    assert readiness.documents_total == 6


def test_missing_column_does_not_also_shout_about_empty_values() -> None:
    """Одна причина — одна проблема, иначе настоящая тонет в шуме."""

    readiness = analyze_pack_readiness(
        mapping={"fio": "нет-колонки"},
        columns=["другое"],
        rows=[{"другое": "x"}, {"другое": "y"}],
        selected_rows=[],
        documents_per_row=1,
        preset_active=True,
    )
    assert "SOURCE_COLUMN_MISSING" in _codes(readiness)
    assert "VALUE_EMPTY" not in _codes(readiness)


def test_literal_mapping_needs_no_column() -> None:
    readiness = analyze_pack_readiness(
        mapping={"city": {"type": "literal", "value": "Москва"}, "fio": "фио"},
        columns=["фио"],
        rows=[{"фио": "Иванов"}],
        selected_rows=[],
        documents_per_row=1,
        preset_active=True,
    )
    assert readiness.ready is True
    assert readiness.problems == ()


def test_unknown_mapping_rule_is_blocking_not_silent() -> None:
    readiness = analyze_pack_readiness(
        mapping={"fio": {"type": "магия", "value": "x"}},
        columns=["фио"],
        rows=[{"фио": "Иванов"}],
        selected_rows=[],
        documents_per_row=1,
        preset_active=True,
    )
    assert readiness.ready is False
    assert _by_code(readiness, "MAPPING_RULE_INVALID").blocking is True


def test_inactive_preset_blocks() -> None:
    readiness = analyze_pack_readiness(
        mapping={"fio": "фио"},
        columns=["фио"],
        rows=[{"фио": "Иванов"}],
        selected_rows=[],
        documents_per_row=1,
        preset_active=False,
    )
    assert readiness.ready is False
    assert "PRESET_NOT_ACTIVE" in _codes(readiness)


def test_preset_without_documents_blocks() -> None:
    readiness = analyze_pack_readiness(
        mapping={"fio": "фио"},
        columns=["фио"],
        rows=[{"фио": "Иванов"}],
        selected_rows=[],
        documents_per_row=0,
        preset_active=True,
    )
    assert readiness.ready is False
    assert "PRESET_HAS_NO_ITEMS" in _codes(readiness)


def test_empty_source_is_zero_percent_not_hundred() -> None:
    """Ноль строк — это ноль готовности, а не «сто процентов из ничего»."""

    readiness = analyze_pack_readiness(
        mapping={"fio": "фио"},
        columns=["фио"],
        rows=[],
        selected_rows=[],
        documents_per_row=1,
        preset_active=True,
    )
    assert readiness.ready is False
    assert readiness.score == 0
    assert "NO_ROWS_SELECTED" in _codes(readiness)


def test_out_of_range_selection_warns_and_does_not_block() -> None:
    """Файл заменили после выбора — строк нет, но остальные сгенерируются."""

    readiness = analyze_pack_readiness(
        mapping={"fio": "фио"},
        columns=["фио"],
        rows=[{"фио": "Иванов"}],
        selected_rows=[1, 7, 99],
        documents_per_row=1,
        preset_active=True,
    )
    assert readiness.ready is True
    problem = _by_code(readiness, "ROWS_OUT_OF_RANGE")
    assert problem.blocking is False
    assert problem.rows == (7, 99)
    assert readiness.rows_selected == 1


def test_problem_rows_are_capped_but_total_is_honest() -> None:
    """Файл на тысячи строк не должен вернуть мегабайт номеров."""

    rows = [{"фио": ""} for _ in range(PROBLEM_ROWS_LIMIT + 25)]
    readiness = analyze_pack_readiness(
        mapping={"fio": "фио"},
        columns=["фио"],
        rows=rows,
        selected_rows=[],
        documents_per_row=1,
        preset_active=True,
    )
    problem = _by_code(readiness, "VALUE_EMPTY")
    assert len(problem.rows) == PROBLEM_ROWS_LIMIT
    # Урезали показ, а не правду.
    assert problem.rows_total == PROBLEM_ROWS_LIMIT + 25
    assert readiness.score == 0
