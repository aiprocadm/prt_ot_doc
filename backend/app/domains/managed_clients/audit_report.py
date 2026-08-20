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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

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
    parts = ", ".join(
        f"{title} — {count}" for title, count in changes_by_kind.items() if count
    )
    return f"Изменений за период: {total} ({parts})."

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
    directions: list[DirectionReadiness], changes_unhandled: int
) -> list[str]:
    actions = [
        f"{row.title}: {row.reason}"
        for row in directions
        if row.light is TrafficLight.RED
    ]
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
) -> AuditReportContent:
    """Собрать отчёт «что изменилось, что просрочено, что нужно сделать»."""

    overall = worst_light(directions)
    actions = _actions(directions, changes_unhandled)
    summary_parts = [
        _changes_block(changes_by_kind),
        _gaps_block(directions),
        (
            "Что нужно сделать: " + "; ".join(actions) + "."
            if actions
            else "Действий не требуется."
        ),
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
            }
            for row in directions
        ],
        "changes": {
            "total": sum(changes_by_kind.values()),
            "by_kind": {k: v for k, v in changes_by_kind.items() if v},
            "unhandled": changes_unhandled,
        },
        "actions": actions,
    }
    return AuditReportContent(
        overall=overall.value,
        summary=" ".join(summary_parts),
        payload=payload,
    )
