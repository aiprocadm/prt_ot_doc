"""BIZ-59 — UX-бюджет записан один раз (ТЗ Доп. №2, разд. 59.2).

Числа бюджета нужны на обеих сторонах: бэкенд объявляет их как часть описания
продукта, фронтенд ими меряет отрисованный экран. Записать их дважды и не
стеречь совпадение значит однажды получить два разных ответа на вопрос
«соблюдён ли бюджет» — и оба «правильных».
"""

from __future__ import annotations

import pathlib
import re

from app.core.product_spec import UX_BUDGET

_TS_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "ux" / "budget.ts"
)

#: Питоновское имя → имя в TypeScript. Явное соответствие, а не автоперевод
#: snake_case → camelCase: опечатка в переименовании превратилась бы в «ключа
#: нет, значит и сверять нечего».
_NAMES = {
    "max_primary_cta": "maxPrimaryCta",
    "max_visible_form_fields": "maxVisibleFormFields",
    "max_default_table_columns": "maxDefaultTableColumns",
    "max_dashboard_blocks": "maxDashboardBlocks",
    "max_nav_depth": "maxNavDepth",
}


def _frontend_budget() -> dict[str, int]:
    text = _TS_PATH.read_text(encoding="utf-8")
    return {
        name: int(value)
        for name, value in re.findall(r"^\s*(\w+):\s*(\d+),", text, flags=re.MULTILINE)
    }


def test_frontend_file_exists() -> None:
    """Без файла тест «совпадает» вхолостую — и мы этого не заметим."""

    assert _TS_PATH.exists(), f"нет {_TS_PATH}"


def test_every_limit_is_declared_on_both_sides() -> None:
    front = _frontend_budget()
    assert set(_NAMES) == set(UX_BUDGET), "список лимитов в product_spec.py изменился"
    for python_name, ts_name in _NAMES.items():
        assert ts_name in front, f"лимит {python_name} не объявлен во фронтенде как {ts_name}"


def test_numbers_are_the_same() -> None:
    """Разойдись числа — «бюджет соблюдён» означало бы разное у ревью и у теста."""

    front = _frontend_budget()
    mismatched = {
        python_name: (UX_BUDGET[python_name], front[ts_name])
        for python_name, ts_name in _NAMES.items()
        if front.get(ts_name) != UX_BUDGET[python_name]
    }
    assert not mismatched, f"числа разошлись (python, ts): {mismatched}"


def test_limits_match_the_spec_table() -> None:
    """Числа из таблицы разд. 59.2 — зафиксированы, чтобы не «поплыли» тихо.

    Поднять лимит можно, но это решение о продукте: оно должно быть видно в
    диффе теста, а не проскочить правкой одной цифры.
    """

    assert UX_BUDGET == {
        "max_primary_cta": 2,
        "max_visible_form_fields": 7,
        "max_default_table_columns": 7,
        "max_dashboard_blocks": 6,
        "max_nav_depth": 3,
    }
