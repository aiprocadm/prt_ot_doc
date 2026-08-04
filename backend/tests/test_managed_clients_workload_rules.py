"""Unit: BIZ-49 срез-5 — правила загрузки специалистов (разд. 49.2, последний блок).

ТЗ: «Сколько клиентов/задач на каждом специалисте; выявление перегруза».
Чистые правила без БД: из чего складывается загрузка, что считается перегрузом
и как в этой картине выглядит работа без ответственного.
"""

from __future__ import annotations

import pytest

from app.domains.managed_clients.workload import (
    DEFAULT_THRESHOLDS,
    UNASSIGNED_KEY,
    OverloadReason,
    WorkloadThresholds,
    build_workload_row,
    sort_workload,
)


def _row(
    person_id=UNASSIGNED_KEY,
    *,
    name=None,
    clients=1,
    critical=0,
    signals=0,
    overdue=0,
    thresholds: WorkloadThresholds | None = None,
):
    return build_workload_row(
        person_id=person_id,
        person_name=name,
        clients_total=clients,
        clients_critical=critical,
        signals_total=signals,
        overdue_deadlines=overdue,
        thresholds=thresholds or DEFAULT_THRESHOLDS,
    )


class TestBuildRow:
    def test_counts_are_carried_as_is(self):
        row = _row("p1", name="Иванов", clients=4, critical=1, signals=12, overdue=3)
        assert (row.clients_total, row.clients_critical) == (4, 1)
        assert (row.signals_total, row.overdue_deadlines) == (12, 3)
        assert row.person_name == "Иванов"

    def test_quiet_specialist_is_not_overloaded(self):
        row = _row("p1", clients=2, signals=1)
        assert row.overloaded is False
        assert row.overload_reasons == []

    def test_unassigned_row_is_marked(self):
        """Работа без ответственного — не «специалист по имени None»: её видно
        отдельной строкой, иначе она молча растворится в общей картине."""
        row = _row(UNASSIGNED_KEY, clients=3, signals=9)
        assert row.unassigned is True
        assert row.person_id == UNASSIGNED_KEY

    def test_named_specialist_is_not_unassigned(self):
        assert _row("p1", name="Иванов").unassigned is False


class TestOverload:
    def test_too_many_clients(self):
        row = _row("p1", clients=DEFAULT_THRESHOLDS.max_clients + 1)
        assert row.overloaded is True
        assert OverloadReason.TOO_MANY_CLIENTS in row.overload_reasons

    def test_exactly_at_threshold_is_not_overload(self):
        """Порог — «не больше чем», а не «начиная с»: иначе норма считается бедой."""
        row = _row("p1", clients=DEFAULT_THRESHOLDS.max_clients)
        assert row.overloaded is False

    def test_too_many_signals(self):
        row = _row("p1", signals=DEFAULT_THRESHOLDS.max_signals + 1)
        assert OverloadReason.TOO_MANY_SIGNALS in row.overload_reasons

    def test_any_critical_client_is_overload(self):
        """Один критический клиент — уже повод вмешаться: там люди не допущены
        к работе, и «в среднем нормально» здесь не аргумент."""
        row = _row("p1", clients=1, critical=1)
        assert row.overloaded is True
        assert OverloadReason.CRITICAL_CLIENT in row.overload_reasons

    def test_overdue_deadlines_threshold(self):
        row = _row("p1", overdue=DEFAULT_THRESHOLDS.max_overdue + 1)
        assert OverloadReason.TOO_MANY_OVERDUE in row.overload_reasons

    def test_reasons_accumulate(self):
        row = _row(
            "p1",
            clients=DEFAULT_THRESHOLDS.max_clients + 5,
            critical=2,
            signals=DEFAULT_THRESHOLDS.max_signals + 10,
        )
        assert len(row.overload_reasons) == 3

    def test_thresholds_are_configurable(self):
        strict = WorkloadThresholds(max_clients=1, max_signals=0, max_overdue=0)
        assert _row("p1", clients=2, thresholds=strict).overloaded is True
        assert _row("p1", clients=1, thresholds=strict).overloaded is False


class TestSort:
    def test_overloaded_first(self):
        rows = [
            _row("тихий", clients=1),
            _row("перегружен", critical=1),
        ]
        assert [r.person_id for r in sort_workload(rows)] == ["перегружен", "тихий"]

    def test_within_same_state_more_signals_first(self):
        rows = [_row("мало", signals=2), _row("много", signals=20)]
        assert [r.person_id for r in sort_workload(rows)] == ["много", "мало"]

    def test_unassigned_goes_last_but_stays_visible(self):
        """Строка «не назначен» не должна перекрывать живых специалистов,
        но и потеряться не должна."""
        rows = [_row(UNASSIGNED_KEY, clients=9, signals=99), _row("p1", signals=1)]
        result = sort_workload(rows)
        assert result[-1].unassigned is True
        assert len(result) == 2

    def test_stable_by_name(self):
        rows = [_row("p2", name="Бета"), _row("p1", name="Альфа")]
        assert [r.person_name for r in sort_workload(rows)] == ["Альфа", "Бета"]


def test_every_reason_has_human_text():
    from app.domains.managed_clients.workload import OVERLOAD_REASON_TEXT

    for reason in OverloadReason:
        assert OVERLOAD_REASON_TEXT[reason].strip()


@pytest.mark.parametrize("clients", [0, 1, 50])
def test_row_survives_any_counts(clients):
    row = _row("p1", clients=clients)
    assert row.clients_total == clients
