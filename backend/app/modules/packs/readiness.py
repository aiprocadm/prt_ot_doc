"""BIZ-50 срез-1 (Доп. №1, разд. 50.2): предпросмотр комплекта до генерации.

Мастер разового комплекта в ТЗ — четыре шага, и третий звучит так:
«предпросмотр состава и readiness — что войдёт в комплект, чего не хватает
и почему». Именно его и не было.

Что происходило без него: специалист заполнял мастер, запускал генерацию и
узнавал о проблеме одним из двух способов — либо ответом 400 «missing source
column for mapping X» на ПЕРВОЙ же нехватке, либо, что хуже, получал комплект
с пустыми местами в документах и отдавал его клиенту. Оба способа плохи
по-разному: первый заставляет чинить пять пропущенных колонок по одной за
прогон, второй превращает брак в подписанный документ.

Здесь чистые правила без БД и без FastAPI.

Три решения, которые важнее кода:

* **предпросмотр НИЧЕГО не создаёт.** Ни строки прогона, ни ключа
  идемпотентности. «Посмотреть, что получится» не должно тратить прогон и
  засорять историю, иначе им перестанут пользоваться ровно тогда, когда он
  нужнее всего — на черновом файле.
* **блокирующее и предупреждение — разные вещи.** Нет колонки под
  обязательное поле — генерация невозможна. Пустое значение в отдельной
  строке — возможна, но документ выйдет с дырой. Смешать их значит либо
  запрещать работу из-за мелочи, либо молча выпускать брак.
* **проблемы перечисляются СПИСКОМ и с потолком.** Список — чтобы починить
  всё за один заход. Потолок — потому что файл на пять тысяч строк иначе
  вернёт мегабайт текста, который никто не прочитает; сверх потолка отдаётся
  число.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PROBLEM_ROWS_LIMIT",
    "PackReadiness",
    "ReadinessProblem",
    "analyze_pack_readiness",
    "mapping_targets",
]

#: Сколько проблемных строк показываем поимённо. Остальные — числом.
PROBLEM_ROWS_LIMIT = 50


@dataclass(frozen=True)
class ReadinessProblem:
    """Одна причина, по которой комплект выйдет не таким, как ждут."""

    code: str
    #: Человеческим языком: что не так И что с этим делать.
    message: str
    #: ``True`` — генерация невозможна; ``False`` — выйдет, но с дырой.
    blocking: bool
    #: Номера строк источника (1-based), которых касается проблема.
    rows: tuple[int, ...] = ()
    #: Сколько строк затронуто всего — включая не поместившиеся в ``rows``.
    rows_total: int = 0


@dataclass(frozen=True)
class PackReadiness:
    """Ответ третьего шага мастера."""

    ready: bool
    #: Доля строк, которые дадут полный документ, в процентах.
    score: int
    documents_total: int
    rows_total: int
    rows_selected: int
    rows_ready: int
    problems: tuple[ReadinessProblem, ...] = field(default_factory=tuple)


def mapping_targets(mapping: dict[str, Any]) -> dict[str, str | None]:
    """Поле документа → колонка источника (или ``None`` для литерала).

    Формат правила исторически трёх видов — строка, ``{"type": "column"}`` и
    ``{"type": "literal"}``. Разбирается он в одном месте, чтобы предпросмотр
    и генерация не разошлись в понимании одного и того же пресета.
    """

    targets: dict[str, str | None] = {}
    for target, source in (mapping or {}).items():
        if isinstance(source, str):
            targets[target] = source.strip().lower()
        elif isinstance(source, dict):
            kind = source.get("type")
            if kind == "column":
                targets[target] = str(source.get("value", "")).strip().lower()
            elif kind == "literal":
                targets[target] = None
            else:
                # Неизвестный вид правила — это не «пустое значение», а
                # сломанный пресет: помечаем отдельной проблемой ниже.
                targets[target] = ""
    return targets


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def analyze_pack_readiness(
    *,
    mapping: dict[str, Any],
    columns: list[str],
    rows: list[dict[str, Any]],
    selected_rows: list[int],
    documents_per_row: int,
    preset_active: bool,
) -> PackReadiness:
    """Посчитать, что получится, и перечислить, чего не хватает."""

    problems: list[ReadinessProblem] = []
    known = {str(name).strip().lower() for name in columns}
    targets = mapping_targets(mapping)

    if not preset_active:
        problems.append(
            ReadinessProblem(
                code="PRESET_NOT_ACTIVE",
                message=(
                    "Пресет комплекта не активен — генерация не запустится. "
                    "Активируйте пресет или выберите другой."
                ),
                blocking=True,
            )
        )

    broken = sorted(target for target, source in targets.items() if source == "")
    if broken:
        problems.append(
            ReadinessProblem(
                code="MAPPING_RULE_INVALID",
                message=(
                    "Правило подстановки задано неизвестным способом для полей: "
                    + ", ".join(broken)
                    + ". Исправьте пресет: допустимы колонка источника или "
                    "фиксированное значение."
                ),
                blocking=True,
            )
        )

    missing_columns = sorted(
        {
            source
            for source in targets.values()
            if source is not None and source != "" and source not in known
        }
    )
    if missing_columns:
        problems.append(
            ReadinessProblem(
                code="SOURCE_COLUMN_MISSING",
                message=(
                    "В источнике нет колонок: "
                    + ", ".join(missing_columns)
                    + ". Добавьте их в файл или переназначьте поля в пресете. "
                    "Перечислены ВСЕ сразу — чтобы не чинить по одной за прогон."
                ),
                blocking=True,
            )
        )

    # Выбор строк: пустой список означает «все», как и при запуске генерации.
    selection = selected_rows or list(range(1, len(rows) + 1))
    valid = [row_no for row_no in selection if 1 <= row_no <= len(rows)]
    out_of_range = [row_no for row_no in selection if row_no not in valid]
    if out_of_range:
        problems.append(
            ReadinessProblem(
                code="ROWS_OUT_OF_RANGE",
                message=(
                    "Выбранных строк нет в источнике — они будут пропущены. "
                    "Похоже, файл заменили после выбора."
                ),
                blocking=False,
                rows=tuple(out_of_range[:PROBLEM_ROWS_LIMIT]),
                rows_total=len(out_of_range),
            )
        )

    if not valid:
        problems.append(
            ReadinessProblem(
                code="NO_ROWS_SELECTED",
                message=(
                    "Не выбрано ни одной строки источника — комплект будет пустым. "
                    "Выберите строки или загрузите файл."
                ),
                blocking=True,
            )
        )

    # Пустые значения считаем ТОЛЬКО по колонкам, которые в источнике есть:
    # иначе одна отсутствующая колонка выдала бы ещё и «пусто во всех строках»
    # и утопила настоящую причину в шуме.
    checkable = {
        target: source
        for target, source in targets.items()
        if source not in (None, "") and source in known
    }
    blank_rows: dict[str, list[int]] = {}
    for row_no in valid:
        row = rows[row_no - 1]
        for target, source in checkable.items():
            if _blank(row.get(source)):
                blank_rows.setdefault(target, []).append(row_no)

    rows_with_blanks = {row_no for numbers in blank_rows.values() for row_no in numbers}
    for target in sorted(blank_rows):
        numbers = blank_rows[target]
        problems.append(
            ReadinessProblem(
                code="VALUE_EMPTY",
                message=(
                    f"Поле «{target}» пустое — документ выйдет с пробелом на этом месте. "
                    "Заполните значение в источнике или задайте фиксированное в пресете."
                ),
                blocking=False,
                rows=tuple(numbers[:PROBLEM_ROWS_LIMIT]),
                rows_total=len(numbers),
            )
        )

    if documents_per_row <= 0:
        problems.append(
            ReadinessProblem(
                code="PRESET_HAS_NO_ITEMS",
                message=(
                    "В пресете нет ни одного документа — генерировать нечего. "
                    "Добавьте шаблоны в состав комплекта."
                ),
                blocking=True,
            )
        )

    rows_ready = len(valid) - len(rows_with_blanks)
    blocking = any(problem.blocking for problem in problems)
    # Ноль строк — это ноль готовности, а не «сто процентов из ничего».
    score = 0 if blocking or not valid else round(rows_ready * 100 / len(valid))
    return PackReadiness(
        ready=not blocking,
        score=score,
        documents_total=0 if blocking else len(valid) * documents_per_row,
        rows_total=len(rows),
        rows_selected=len(valid),
        rows_ready=max(0, rows_ready),
        problems=tuple(problems),
    )
