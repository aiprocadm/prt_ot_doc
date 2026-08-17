"""BIZ-51 срез-3: правила превращения просрочек Data Quality в сигналы ленты.

Правила чистые (без базы) — проверяются построчно, как и правила diff'а
импорта в ``tests/test_client_change_signals.py``. Здесь закрепляется:

* просрочка любой из четырёх сущностей даёт вид «Наступает срок» — строку
  таблицы разд. 51.1, а не выдуманный девятый вид;
* дата изменения — день истечения срока, а не день проверки;
* личность находки (``source_ref``) включает дату: тот же срок не плодит
  дубликатов, а продлённая и снова просроченная запись даёт новый сигнал;
* факт без компании или без даты сигнала не даёт.
"""

from __future__ import annotations

from datetime import date

from app.domains.managed_clients.change_feed import ClientChangeKind
from app.domains.managed_clients.dq_signals import (
    EXPIRY_ENTITY_TITLES,
    ExpiryFact,
    signals_for_expiries,
    source_ref_for,
)

COMPANY = "c0000000-0000-0000-0000-000000000001"


def _fact(**overrides) -> ExpiryFact:
    base = dict(
        entity_type="medical_exam",
        entity_id="e0000000-0000-0000-0000-000000000001",
        company_id=COMPANY,
        person_title="Иванов Иван",
        expired_on=date(2026, 5, 1),
    )
    base.update(overrides)
    return ExpiryFact(**base)


class TestKindAndWording:
    def test_вид_у_всех_наступает_срок(self) -> None:
        facts = [
            _fact(entity_type="medical_exam"),
            _fact(entity_type="training"),
            _fact(entity_type="permit"),
            _fact(entity_type="ppe_issue"),
        ]
        signals = signals_for_expiries(facts)
        assert len(signals) == 4
        assert {s.kind for s in signals} == {ClientChangeKind.DEADLINE_APPROACHING}

    def test_сводка_читается_с_вида_изменения(self) -> None:
        by_type = {
            "medical_exam": "Просрочен медосмотр: Иванов Иван",
            "training": "Просрочено обучение: Иванов Иван",
            "permit": "Просрочен допуск: Иванов Иван",
            "ppe_issue": "Просрочены СИЗ: Иванов Иван",
        }
        for entity_type, expected in by_type.items():
            (signal,) = signals_for_expiries([_fact(entity_type=entity_type)])
            assert signal.summary == expected

    def test_подробности_несут_дату_и_предмет(self) -> None:
        (signal,) = signals_for_expiries([_fact(entity_type="ppe_issue", subject="Каска")])
        assert signal.details is not None
        assert "01.05.2026" in signal.details
        assert "Каска" in signal.details

    def test_длинное_имя_обрезается_хвостом(self) -> None:
        (signal,) = signals_for_expiries([_fact(person_title="Х" * 300)])
        assert len(signal.summary) <= 255
        assert signal.summary.startswith("Просрочен медосмотр")
        assert signal.summary.endswith("…")


class TestDates:
    def test_дата_изменения_это_день_истечения(self) -> None:
        (signal,) = signals_for_expiries([_fact(expired_on=date(2026, 3, 15))])
        assert signal.happened_on == date(2026, 3, 15)


class TestIdentity:
    def test_личность_включает_сущность_запись_и_дату(self) -> None:
        fact = _fact()
        assert source_ref_for(fact) == (
            "dq:medical_exam:e0000000-0000-0000-0000-000000000001:2026-05-01"
        )

    def test_тот_же_срок_даёт_ту_же_личность(self) -> None:
        assert source_ref_for(_fact()) == source_ref_for(_fact())

    def test_новый_срок_даёт_новую_личность(self) -> None:
        prolonged = _fact(expired_on=date(2027, 5, 1))
        assert source_ref_for(_fact()) != source_ref_for(prolonged)

    def test_личность_едет_в_сигнале(self) -> None:
        fact = _fact()
        (signal,) = signals_for_expiries([fact])
        assert signal.source_ref == source_ref_for(fact)


class TestDropped:
    def test_без_компании_сигнала_нет(self) -> None:
        assert signals_for_expiries([_fact(company_id=None)]) == ()

    def test_без_даты_сигнала_нет(self) -> None:
        assert signals_for_expiries([_fact(expired_on=None)]) == ()

    def test_незнакомая_сущность_отбрасывается(self) -> None:
        assert signals_for_expiries([_fact(entity_type="document")]) == ()


class TestVocabularyGuard:
    """Сторож словаря: новая сущность обязана получить и название, и сводку.

    Рассинхрон двух словарей в одном модуле уже стоил срезу-2 молчаливо пустой
    ленты — здесь та же защита: сводка строится по закрытому словарю, и пункт
    без формулировки уронит правило на этапе теста, а не молча.
    """

    def test_каждая_сущность_словаря_даёт_сводку(self) -> None:
        for entity_type in EXPIRY_ENTITY_TITLES:
            (signal,) = signals_for_expiries([_fact(entity_type=entity_type)])
            assert signal.summary.startswith("Просрочен")
