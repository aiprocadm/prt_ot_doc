"""BIZ-49 срез-5 (разд. 49.2): правила загрузки специалистов аутсорсера.

ТЗ: «Сколько клиентов/задач на каждом специалисте ОТ/ПБ/эколога; выявление
перегруза». Чистые правила без БД; три вещи решаются здесь, а не в интерфейсе:

* **перегруз — объявленное правило, а не «на глаз».** Пороги вынесены в
  ``WorkloadThresholds`` и попадают в ответ вместе с причинами: руководитель
  должен видеть, ПОЧЕМУ строка красная, иначе он не согласится с выводом;
* **один критический клиент — уже перегруз.** Там люди не допущены к работе,
  и «в среднем нагрузка нормальная» этого не отменяет;
* **работа без ответственного видна отдельной строкой.** Клиенты без
  назначенного специалиста — это не «ничья нагрузка», а самая опасная её
  часть: за неё никто не отвечает. Растворить её в общей картине значит
  спрятать.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

__all__ = [
    "DEFAULT_THRESHOLDS",
    "OVERLOAD_REASON_TEXT",
    "UNASSIGNED_KEY",
    "OverloadReason",
    "SpecialistWorkload",
    "WorkloadThresholds",
    "build_workload_row",
    "sort_workload",
]

#: Ключ строки «клиенты без ответственного».
UNASSIGNED_KEY = "__unassigned__"


class OverloadReason(str, enum.Enum):
    TOO_MANY_CLIENTS = "too_many_clients"
    TOO_MANY_SIGNALS = "too_many_signals"
    TOO_MANY_OVERDUE = "too_many_overdue"
    CRITICAL_CLIENT = "critical_client"


OVERLOAD_REASON_TEXT: dict[OverloadReason, str] = {
    OverloadReason.TOO_MANY_CLIENTS: "Слишком много клиентов на одном специалисте",
    OverloadReason.TOO_MANY_SIGNALS: "Слишком много открытых сигналов",
    OverloadReason.TOO_MANY_OVERDUE: "Слишком много просроченных сроков",
    OverloadReason.CRITICAL_CLIENT: "Есть клиент в критическом состоянии",
}


@dataclass(frozen=True)
class WorkloadThresholds:
    """Пороги перегруза. Сравнение строго «больше», а не «не меньше»:
    ровно на пороге — это ещё норма, и красить её нельзя."""

    max_clients: int = 8
    max_signals: int = 25
    max_overdue: int = 10


DEFAULT_THRESHOLDS = WorkloadThresholds()


@dataclass(frozen=True)
class SpecialistWorkload:
    person_id: str
    person_name: str | None
    unassigned: bool
    clients_total: int
    clients_critical: int
    signals_total: int
    overdue_deadlines: int
    overloaded: bool
    overload_reasons: list[OverloadReason] = field(default_factory=list)


def build_workload_row(
    *,
    person_id: str,
    person_name: str | None,
    clients_total: int,
    clients_critical: int,
    signals_total: int,
    overdue_deadlines: int,
    thresholds: WorkloadThresholds = DEFAULT_THRESHOLDS,
) -> SpecialistWorkload:
    reasons: list[OverloadReason] = []
    if clients_total > thresholds.max_clients:
        reasons.append(OverloadReason.TOO_MANY_CLIENTS)
    if signals_total > thresholds.max_signals:
        reasons.append(OverloadReason.TOO_MANY_SIGNALS)
    if overdue_deadlines > thresholds.max_overdue:
        reasons.append(OverloadReason.TOO_MANY_OVERDUE)
    if clients_critical > 0:
        reasons.append(OverloadReason.CRITICAL_CLIENT)

    return SpecialistWorkload(
        person_id=person_id,
        person_name=person_name,
        unassigned=person_id == UNASSIGNED_KEY,
        clients_total=clients_total,
        clients_critical=clients_critical,
        signals_total=signals_total,
        overdue_deadlines=overdue_deadlines,
        overloaded=bool(reasons),
        overload_reasons=reasons,
    )


def sort_workload(rows: list[SpecialistWorkload]) -> list[SpecialistWorkload]:
    """Перегруженные сверху; «не назначен» — последней, но не скрыт."""

    return sorted(
        rows,
        key=lambda r: (
            1 if r.unassigned else 0,
            0 if r.overloaded else 1,
            -r.signals_total,
            -r.clients_total,
            r.person_name or r.person_id,
        ),
    )
