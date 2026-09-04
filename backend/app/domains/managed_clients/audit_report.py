"""BIZ-51 срез-7 (Доп. №1 разд. 51.3): сборка отчёта авто-аудита.

ТЗ: «периодический авто-аудит — регулярная сверка с формированием отчёта:
что изменилось, что просрочено, что нужно сделать». Кирпичи готовы
предыдущими срезами: светофор (срез-5) отвечает «что просрочено и чего нет»,
лента (срезы 1–3) — «что изменилось», подсказки видов — «что делать».
Здесь эти три ответа собираются в ОДИН текст; правила чистые, без базы.

## Решения

**1. Отчёт всегда о трёх вопросах, даже когда ответ «ничего».** «Изменений не
зафиксировано» и «разрывов не найдено» — это содержание отчёта, а не повод его
не писать: молчание аудита неотличимо от неработающего аудита (довод ленты
DQ: тот же, что у `starter_pack_skipped`).

**2. «Что нужно сделать» выводится, а не сочиняется.** Действия берутся из
расшифровок красных направлений и из числа неразобранных записей ленты —
у каждого действия виден источник. Выдуманный список дел без опоры на числа
разошёлся бы с экраном светофора при первой же правке правил.

**3. Светофор в отчёте — снимок, а не ссылка.** Отчёт хранит числа НА ДАТУ:
ценность аудита в динамике между неделями, пересчёт задним числом её стирает.

**4. Происшествия — отдельным числом, а не цветом (BIZ-54-57 срез-52, Доп. №1
разд. 57.4 «отчёт о состоянии по каждой дисциплине для заказчика»).** Светофор
отвечает «положенное действует?» — открытое ДТП норму медосмотра не
отменяет, и красить им дисциплину значило бы смешать два разных вопроса.
Поэтому открытые происшествия дисциплины идут своим числом в строке, своим
блоком в тексте и своей строкой в действиях; цвет от них не меняется.
Формула «открытое» — общая с дашбордом директора (``open_incidents_where``),
считаются только размеченные; неразмеченные названы отдельно, а не спрятаны
в «охрану труда».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.domains.managed_clients.readiness import (
    DirectionReadiness,
    TrafficLight,
    worst_light,
)

__all__ = ["AuditReportContent", "build_report"]


@dataclass(frozen=True)
class AuditReportContent:
    overall: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)


def _changes_block(changes_by_kind: Mapping[str, int]) -> str:
    total = sum(changes_by_kind.values())
    if total == 0:
        return "Изменений за период не зафиксировано."
    parts = ", ".join(f"{title} — {count}" for title, count in changes_by_kind.items() if count)
    return f"Изменений за период: {total} ({parts})."


_INCIDENT_FORMS = ("происшествие", "происшествия", "происшествий")
_TITLE_BY_CODE = {d.value: DISCIPLINE_TITLES[d] for d in Discipline}


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    tail = abs(count) % 100
    unit = tail % 10
    if 11 <= tail <= 19 or unit == 0 or unit >= 5:
        word = forms[2]
    elif unit == 1:
        word = forms[0]
    else:
        word = forms[1]
    return f"{count} {word}"


def _incidents_block(incidents_open: Mapping[str, int], incidents_unmarked: int) -> str:
    marked = {code: n for code, n in incidents_open.items() if n}
    total = sum(marked.values()) + incidents_unmarked
    if total == 0:
        return "Открытых происшествий нет."
    parts = [f"{_TITLE_BY_CODE.get(code, code)} — {n}" for code, n in marked.items()]
    if incidents_unmarked:
        parts.append(f"не размечено — {incidents_unmarked}")
    return f"Открытых происшествий: {total} ({'; '.join(parts)})."


def _gaps_block(directions: list[DirectionReadiness]) -> str:
    problems = [
        f"{row.title}: {row.reason}"
        for row in directions
        if row.light in (TrafficLight.RED, TrafficLight.YELLOW)
    ]
    if not problems:
        return "Разрывов с эталоном не найдено."
    return "Просрочено и не оформлено — " + "; ".join(problems) + "."


def _actions(
    directions: list[DirectionReadiness],
    changes_unhandled: int,
    incidents_open: Mapping[str, int],
    incidents_unmarked: int,
) -> list[str]:
    actions = [f"{row.title}: {row.reason}" for row in directions if row.light is TrafficLight.RED]
    # Источник каждого действия виден: дисциплина и её число из блока
    # происшествий, а не общее «разобраться».
    for row in directions:
        count = incidents_open.get(row.discipline.value, 0)
        if count:
            actions.append(f"{row.title}: довести до закрытия {_plural(count, _INCIDENT_FORMS)}")
    if incidents_unmarked:
        actions.append(f"Разметить дисциплиной в реестре происшествий: {incidents_unmarked}")
    if changes_unhandled:
        actions.append(f"Разобрать записи ленты изменений: {changes_unhandled}")
    return actions


def build_report(
    *,
    period_start: date,
    period_end: date,
    directions: list[DirectionReadiness],
    changes_by_kind: Mapping[str, int],
    changes_unhandled: int,
    incidents_open: Mapping[str, int] | None = None,
    incidents_unmarked: int = 0,
) -> AuditReportContent:
    """Собрать отчёт «что изменилось, что просрочено, что нужно сделать».

    ``incidents_open`` — открытые происшествия по коду дисциплины,
    ``incidents_unmarked`` — без разметки (срез-52). Цвет от них не зависит.
    """

    incidents_open = dict(incidents_open or {})
    overall = worst_light(directions)
    actions = _actions(directions, changes_unhandled, incidents_open, incidents_unmarked)
    summary_parts = [
        _changes_block(changes_by_kind),
        _gaps_block(directions),
        _incidents_block(incidents_open, incidents_unmarked),
        ("Что нужно сделать: " + "; ".join(actions) + "." if actions else "Действий не требуется."),
    ]
    payload: dict[str, Any] = {
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "directions": [
            {
                "direction": row.discipline.value,
                "title": row.title,
                "light": row.light.value,
                "reason": row.reason,
                "required": row.counts.required,
                "missing": row.counts.missing,
                "lapsed": row.counts.lapsed,
                "expiring": row.counts.expiring,
                "incidents_open": incidents_open.get(row.discipline.value, 0),
            }
            for row in directions
        ],
        "changes": {
            "total": sum(changes_by_kind.values()),
            "by_kind": {k: v for k, v in changes_by_kind.items() if v},
            "unhandled": changes_unhandled,
        },
        "incidents": {
            "total": sum(incidents_open.values()) + incidents_unmarked,
            "by_discipline": {k: v for k, v in incidents_open.items() if v},
            "unmarked": incidents_unmarked,
        },
        "actions": actions,
    }
    return AuditReportContent(
        overall=overall.value,
        summary=" ".join(summary_parts),
        payload=payload,
    )
