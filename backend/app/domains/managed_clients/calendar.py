"""BIZ-49 срез-4 (разд. 49.2): правила единого календаря дедлайнов по портфелю.

Чистые правила без БД. ТЗ требует «единый календарь дедлайнов по всем клиентам
с фильтром по клиенту/специалисту/типу», и три вещи здесь нельзя отдать
интерфейсу:

* **просроченное не уезжает вниз.** Дата в прошлом — не повод показать событие
  последним: просроченный медосмотр это самое срочное, что есть в календаре.
  Сортировка ставит просрочку первой, а не «хронологически честно»;
* **«сегодня» — ещё не просрочка.** Срок можно закрыть сегодняшним днём, и
  красить его в красный значит приучить не верить красному;
* **вес вида дедлайна.** В один день сверху идёт то, что тяжелее: медосмотр
  раньше договора — во втором случае страдает бумага, в первом человек.

Удостоверения водителей (BIZ-54-57 срез-91, разд. 54.1 / 56.2) — дата
``license_due`` допущенных к управлению водителей организации клиента; вес —
как у медосмотра: истёкшее удостоверение — это не «нарушение к проверке», а
остановка перевозок (тот же ряд, что сигнал ``driver_license_expired`` в
сводке внимания, срез-88): специалист видел сигнал, но не видел даты.

Пожарная безопасность (срез-92, разд. 54.1) — один вид на все слагаемые
(перезарядка и поверка средств, тренировки, пересмотр документов,
противопожарные инструктажи), как один сигнал ``fire_safety_overdue`` в
сводке: «что именно и где» — в предмете события. Вес — как у СИЗ и
обучения: нарушение к приходу МЧС, но не отстранение человека.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date

__all__ = [
    "DEADLINE_META",
    "CalendarFilters",
    "DeadlineEvent",
    "DeadlineKind",
    "DeadlineDay",
    "apply_filters",
    "build_event",
    "group_by_date",
    "sort_deadlines",
]


class DeadlineKind(str, enum.Enum):
    MEDICAL = "medical"
    PPE = "ppe"
    TRAINING = "training"
    CONTRACT = "contract"
    DRIVER_LICENSE = "driver_license"
    FIRE_SAFETY = "fire_safety"


@dataclass(frozen=True)
class DeadlineMeta:
    title: str
    #: Чем больше, тем выше в пределах одного дня.
    weight: int


DEADLINE_META: dict[DeadlineKind, DeadlineMeta] = {
    DeadlineKind.MEDICAL: DeadlineMeta(title="Медосмотр", weight=4),
    # Удостоверение — допуск к управлению, как медосмотр — допуск к работе.
    DeadlineKind.DRIVER_LICENSE: DeadlineMeta(title="Удостоверение водителя", weight=4),
    DeadlineKind.PPE: DeadlineMeta(title="Срок СИЗ", weight=3),
    DeadlineKind.TRAINING: DeadlineMeta(title="Обучение", weight=3),
    DeadlineKind.CONTRACT: DeadlineMeta(title="Договор", weight=2),
    DeadlineKind.FIRE_SAFETY: DeadlineMeta(title="Пожарная безопасность", weight=3),
}


@dataclass(frozen=True)
class DeadlineEvent:
    kind: DeadlineKind
    title: str
    due_date: date
    client_id: str
    client_name: str
    #: Кого/чего касается: ФИО сотрудника, название СИЗ, номер договора.
    subject: str
    responsible_person_id: str | None
    days_left: int
    overdue: bool


@dataclass(frozen=True)
class DeadlineDay:
    due_date: date
    overdue: bool
    events: list[DeadlineEvent] = field(default_factory=list)


@dataclass(frozen=True)
class CalendarFilters:
    """Фильтры разд. 49.2: по клиенту, специалисту и типу."""

    client_id: str | None = None
    responsible_person_id: str | None = None
    kinds: set[DeadlineKind] | None = None


def build_event(
    *,
    kind: DeadlineKind,
    due_date: date,
    client_id: str,
    client_name: str,
    subject: str,
    responsible_person_id: str | None,
    today: date,
) -> DeadlineEvent:
    days_left = (due_date - today).days
    return DeadlineEvent(
        kind=kind,
        title=DEADLINE_META[kind].title,
        due_date=due_date,
        client_id=client_id,
        client_name=client_name,
        subject=subject,
        responsible_person_id=responsible_person_id,
        days_left=days_left,
        # Строго меньше нуля: срок «сегодня» ещё можно закрыть.
        overdue=days_left < 0,
    )


def sort_deadlines(events: list[DeadlineEvent]) -> list[DeadlineEvent]:
    """Просроченное первым (от самого давнего), затем ближайшее по дате."""

    return sorted(
        events,
        key=lambda e: (
            0 if e.overdue else 1,
            e.due_date,
            -DEADLINE_META[e.kind].weight,
            e.client_name,
            e.subject,
        ),
    )


def apply_filters(events: list[DeadlineEvent], filters: CalendarFilters) -> list[DeadlineEvent]:
    """Фильтры комбинируются как И: пустой результат честнее «показать всё»."""

    result = events
    if filters.client_id:
        result = [e for e in result if e.client_id == filters.client_id]
    if filters.responsible_person_id:
        result = [e for e in result if e.responsible_person_id == filters.responsible_person_id]
    if filters.kinds:
        result = [e for e in result if e.kind in filters.kinds]
    return result


def group_by_date(events: list[DeadlineEvent]) -> list[DeadlineDay]:
    """Сгруппировать УЖЕ отсортированные события по дню, сохранив их порядок."""

    days: dict[date, list[DeadlineEvent]] = {}
    for event in events:
        days.setdefault(event.due_date, []).append(event)
    return [
        DeadlineDay(due_date=day, overdue=items[0].overdue, events=items)
        for day, items in sorted(days.items())
    ]
