"""Unit: BIZ-49 срез-2 — правила сводного «Центра внимания» по портфелю (разд. 49.2).

Чистые правила без БД: как сигналы клиента складываются в строку портфеля,
как строки упорядочиваются («где горит сильнее» — сверху) и чем статус
«не агрегируется» отличается от «всё чисто».
"""

from __future__ import annotations

import pytest

from app.domains.managed_clients.attention import (
    AggregationStatus,
    ClientAttention,
    Severity,
    SignalKind,
    build_client_attention,
    not_aggregated,
    sort_portfolio,
)


def _counts(**over) -> dict[SignalKind, int]:
    base = {kind: 0 for kind in SignalKind}
    base.update(over)
    return base


class TestBuildClientAttention:
    def test_no_signals_is_clean_but_aggregated(self):
        row = build_client_attention(
            client_id="mc1", client_name="Ромашка", counts=_counts(), contract_expiring=False
        )
        assert row.aggregation is AggregationStatus.AGGREGATED
        assert row.signals == []
        assert row.total == 0
        assert row.severity is None

    def test_signals_carry_counts_and_severity(self):
        row = build_client_attention(
            client_id="mc1",
            client_name="Ромашка",
            counts=_counts(**{SignalKind.TRAINING_OVERDUE: 3, SignalKind.CONTACTS_MISSING: 2}),
            contract_expiring=False,
        )
        kinds = {s.kind: s for s in row.signals}
        assert kinds[SignalKind.TRAINING_OVERDUE].count == 3
        assert kinds[SignalKind.CONTACTS_MISSING].count == 2
        assert row.total == 5

    def test_zero_count_signal_is_omitted(self):
        """Нулевой сигнал в списке — визуальный шум, за которым теряются настоящие."""
        row = build_client_attention(
            client_id="mc1",
            client_name="Ромашка",
            counts=_counts(**{SignalKind.PPE_OVERDUE: 1}),
            contract_expiring=False,
        )
        assert [s.kind for s in row.signals] == [SignalKind.PPE_OVERDUE]

    def test_client_severity_is_the_worst_of_its_signals(self):
        row = build_client_attention(
            client_id="mc1",
            client_name="Ромашка",
            counts=_counts(**{SignalKind.CONTACTS_MISSING: 10, SignalKind.MEDICAL_OVERDUE: 1}),
            contract_expiring=False,
        )
        # медосмотр — критический сигнал (человек не допущен к работе),
        # контакты — низкий; десять «низких» не перевешивают один критический
        assert row.severity is Severity.CRITICAL

    def test_contract_expiring_is_a_signal_too(self):
        row = build_client_attention(
            client_id="mc1", client_name="Ромашка", counts=_counts(), contract_expiring=True
        )
        assert [s.kind for s in row.signals] == [SignalKind.CONTRACT_EXPIRING]
        assert row.total == 1
        assert row.severity is Severity.HIGH

    def test_signals_are_ordered_by_severity_then_count(self):
        row = build_client_attention(
            client_id="mc1",
            client_name="Ромашка",
            counts=_counts(
                **{
                    SignalKind.CONTACTS_MISSING: 9,
                    SignalKind.MEDICAL_OVERDUE: 1,
                    SignalKind.TRAINING_OVERDUE: 4,
                }
            ),
            contract_expiring=False,
        )
        assert [s.kind for s in row.signals] == [
            SignalKind.MEDICAL_OVERDUE,
            SignalKind.TRAINING_OVERDUE,
            SignalKind.CONTACTS_MISSING,
        ]


class TestNotAggregated:
    def test_dedicated_client_is_not_silently_zero(self):
        """Клиент со своим контуром: данные в другом арендаторе. Ноль здесь
        читался бы как «у клиента всё хорошо» — это ложь, а не осторожность."""
        row = not_aggregated(
            client_id="mc2", client_name="Крупный", reason="Данные в отдельном контуре клиента"
        )
        assert row.aggregation is AggregationStatus.NOT_AGGREGATED
        assert row.signals == []
        assert row.total is None  # именно None, а не 0
        assert row.reason


class TestSortPortfolio:
    def _row(self, cid, *, critical=0, high=0, aggregated=True) -> ClientAttention:
        if not aggregated:
            return not_aggregated(client_id=cid, client_name=cid, reason="—")
        return build_client_attention(
            client_id=cid,
            client_name=cid,
            counts=_counts(
                **{SignalKind.MEDICAL_OVERDUE: critical, SignalKind.TRAINING_OVERDUE: high}
            ),
            contract_expiring=False,
        )

    def test_worst_first(self):
        rows = [
            self._row("тихий"),
            self._row("средний", high=2),
            self._row("горит", critical=1),
        ]
        assert [r.client_id for r in sort_portfolio(rows)] == ["горит", "средний", "тихий"]

    def test_same_severity_more_items_first(self):
        rows = [self._row("мало", high=1), self._row("много", high=7)]
        assert [r.client_id for r in sort_portfolio(rows)] == ["много", "мало"]

    def test_not_aggregated_sits_above_the_quiet_ones(self):
        """«Не смотрели» важнее «всё чисто»: это работа, а не спокойствие."""
        rows = [self._row("чистый"), self._row("неизвестный", aggregated=False)]
        assert [r.client_id for r in sort_portfolio(rows)] == ["неизвестный", "чистый"]

    def test_stable_by_name_within_equal_weight(self):
        rows = [self._row("бета"), self._row("альфа")]
        assert [r.client_id for r in sort_portfolio(rows)] == ["альфа", "бета"]


def test_signal_kinds_all_have_severity_and_title():
    """Новый вид сигнала без веса и названия молча уехал бы вниз списка."""
    from app.domains.managed_clients.attention import SIGNAL_META

    for kind in SignalKind:
        meta = SIGNAL_META[kind]
        assert isinstance(meta.severity, Severity)
        assert meta.title.strip()
        assert meta.action_hint.strip()


@pytest.mark.parametrize(
    "worse,better",
    [
        (Severity.CRITICAL, Severity.HIGH),
        (Severity.HIGH, Severity.MEDIUM),
        (Severity.MEDIUM, Severity.LOW),
    ],
)
def test_severity_ordering(worse, better):
    assert worse.weight > better.weight
