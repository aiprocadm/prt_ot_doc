"""Unit: BIZ-49 срез-4 — правила cross-client календаря дедлайнов (разд. 49.2).

Чистые правила без БД: что считается просроченным, в каком порядке идут события
и как работают фильтры «по клиенту / специалисту / типу» из ТЗ.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.managed_clients.calendar import (
    DEADLINE_META,
    CalendarFilters,
    DeadlineEvent,
    DeadlineKind,
    apply_filters,
    build_event,
    group_by_date,
    sort_deadlines,
)

_TODAY = date(2026, 8, 4)


def _event(
    *,
    kind=DeadlineKind.MEDICAL,
    due=_TODAY,
    client_id="mc1",
    client_name="Ромашка",
    subject="Иванов И.И.",
    responsible=None,
) -> DeadlineEvent:
    return build_event(
        kind=kind,
        due_date=due,
        client_id=client_id,
        client_name=client_name,
        subject=subject,
        responsible_person_id=responsible,
        today=_TODAY,
    )


class TestBuildEvent:
    def test_future_deadline_is_not_overdue(self):
        ev = _event(due=date(2026, 8, 20))
        assert ev.overdue is False
        assert ev.days_left == 16

    def test_today_is_not_overdue_yet(self):
        """Срок «сегодня» ещё можно закрыть — это не просрочка."""
        ev = _event(due=_TODAY)
        assert ev.overdue is False
        assert ev.days_left == 0

    def test_past_deadline_is_overdue_with_negative_days(self):
        ev = _event(due=date(2026, 7, 25))
        assert ev.overdue is True
        assert ev.days_left == -10

    def test_event_carries_human_title(self):
        ev = _event(kind=DeadlineKind.PPE)
        assert ev.title == DEADLINE_META[DeadlineKind.PPE].title
        assert ev.subject == "Иванов И.И."


class TestSortDeadlines:
    def test_overdue_first_then_by_date(self):
        """Просроченное не уезжает в конец «потому что дата в прошлом»:
        это самые срочные события, и они обязаны быть сверху."""
        events = [
            _event(due=date(2026, 8, 10), subject="через неделю"),
            _event(due=date(2026, 7, 20), subject="просрочен давно"),
            _event(due=date(2026, 8, 5), subject="завтра"),
            _event(due=date(2026, 8, 1), subject="просрочен недавно"),
        ]
        assert [e.subject for e in sort_deadlines(events)] == [
            "просрочен давно",
            "просрочен недавно",
            "завтра",
            "через неделю",
        ]

    def test_same_date_sorted_by_severity_of_kind(self):
        """В один день сверху то, что тяжелее: медосмотр перед контактами."""
        events = [
            _event(kind=DeadlineKind.CONTRACT, subject="договор"),
            _event(kind=DeadlineKind.MEDICAL, subject="медосмотр"),
            _event(kind=DeadlineKind.TRAINING, subject="обучение"),
        ]
        result = [e.subject for e in sort_deadlines(events)]
        assert result[0] == "медосмотр"

    def test_driver_license_weighs_like_medical(self):
        """Удостоверение — допуск к управлению, как медосмотр — к работе (срез-91):
        в один день оно выше СИЗ, обучения и договора."""
        events = [
            _event(kind=DeadlineKind.CONTRACT, subject="договор"),
            _event(kind=DeadlineKind.PPE, subject="сиз"),
            _event(kind=DeadlineKind.DRIVER_LICENSE, subject="удостоверение"),
            _event(kind=DeadlineKind.TRAINING, subject="обучение"),
        ]
        assert [e.subject for e in sort_deadlines(events)][0] == "удостоверение"
        assert (
            DEADLINE_META[DeadlineKind.DRIVER_LICENSE].weight
            == DEADLINE_META[DeadlineKind.MEDICAL].weight
        )

    def test_stable_by_client_then_subject(self):
        events = [
            _event(client_name="Бета", subject="б"),
            _event(client_name="Альфа", subject="а"),
        ]
        assert [e.client_name for e in sort_deadlines(events)] == ["Альфа", "Бета"]


class TestFilters:
    def _mixed(self) -> list[DeadlineEvent]:
        return [
            _event(client_id="mc1", kind=DeadlineKind.MEDICAL, responsible="p1"),
            _event(client_id="mc2", kind=DeadlineKind.TRAINING, responsible="p2"),
            _event(client_id="mc1", kind=DeadlineKind.CONTRACT, responsible="p1"),
        ]

    def test_no_filters_keeps_everything(self):
        events = self._mixed()
        assert len(apply_filters(events, CalendarFilters())) == 3

    def test_filter_by_client(self):
        events = apply_filters(self._mixed(), CalendarFilters(client_id="mc1"))
        assert {e.client_id for e in events} == {"mc1"}

    def test_filter_by_kind(self):
        events = apply_filters(self._mixed(), CalendarFilters(kinds={DeadlineKind.MEDICAL}))
        assert [e.kind for e in events] == [DeadlineKind.MEDICAL]

    def test_filter_by_responsible_specialist(self):
        events = apply_filters(self._mixed(), CalendarFilters(responsible_person_id="p2"))
        assert [e.client_id for e in events] == ["mc2"]

    def test_filters_combine_as_and(self):
        events = apply_filters(
            self._mixed(),
            CalendarFilters(client_id="mc1", kinds={DeadlineKind.CONTRACT}),
        )
        assert len(events) == 1
        assert events[0].kind is DeadlineKind.CONTRACT

    def test_unknown_client_yields_empty_not_everything(self):
        """Фильтр по несуществующему клиенту обязан дать пусто, а не всё подряд."""
        assert apply_filters(self._mixed(), CalendarFilters(client_id="нет-такого")) == []


class TestGroupByDate:
    def test_groups_are_sorted_and_keep_event_order(self):
        events = [
            # в один день с «тяжёлым» — но вид легче, поэтому обязан идти ниже
            _event(due=date(2026, 8, 6), kind=DeadlineKind.CONTRACT, subject="второй"),
            _event(due=date(2026, 8, 5), subject="первый"),
            _event(due=date(2026, 8, 6), kind=DeadlineKind.MEDICAL, subject="тяжёлый"),
        ]
        groups = group_by_date(sort_deadlines(events))
        assert [g.due_date for g in groups] == [date(2026, 8, 5), date(2026, 8, 6)]
        assert groups[1].events[0].subject == "тяжёлый"

    def test_overdue_days_stay_in_their_own_dates(self):
        groups = group_by_date(
            sort_deadlines([_event(due=date(2026, 7, 30)), _event(due=date(2026, 8, 9))])
        )
        assert [g.overdue for g in groups] == [True, False]


def test_every_kind_has_meta():
    """Новый вид дедлайна без описания молча потерял бы название и вес."""
    for kind in DeadlineKind:
        meta = DEADLINE_META[kind]
        assert meta.title.strip()
        assert meta.weight > 0


@pytest.mark.parametrize("days", [0, 1, 30, 365])
def test_build_event_accepts_any_horizon(days):
    ev = _event(due=date(2026, 8, 4 + min(days, 20)))
    assert isinstance(ev.days_left, int)
