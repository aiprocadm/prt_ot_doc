"""BIZ-51 срез-5: правила светофора соответствия (разд. 51.3).

Правила чистые — проверяются построчно. Закрепляется:

* зелёное — только доказанное: пустой эталон даёт «эталон не задан», а не
  зелёный;
* «не было вовсе» и «было, но не действует» — разные числа расшифровки;
* итог клиента — по худшему ИЗМЕРЕННОМУ направлению, «не измеряется» итог
  не портит;
* порядок направлений фиксированный — светофор сравнивают неделю с неделей.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.domains.managed_clients.readiness import (
    Direction,
    DirectionCounts,
    TrafficLight,
    build_directions,
    evaluate_direction,
    training_readiness,
    worst_light,
)
# Правила счёта переехали в общий сервис (BIZ-54-57 срез-3): тот же счёт
# ведёт карточка площадки, поэтому проверяются они там, где живут.
from app.services.discipline_numbers import _medical_counts, _ppe_counts

TODAY = date(2026, 8, 17)
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
HORIZON = timedelta(days=30)


class TestEvaluateDirection:
    def test_пустой_эталон_это_не_зелёный(self) -> None:
        light, reason = evaluate_direction(DirectionCounts())
        assert light is TrafficLight.NOT_MEASURED
        assert "Эталон не задан" in reason

    def test_разрыв_красит_красным_с_расшифровкой(self) -> None:
        light, reason = evaluate_direction(
            DirectionCounts(required=5, missing=2, lapsed=1)
        )
        assert light is TrafficLight.RED
        assert "не оформлено вовсе: 2" in reason
        assert "истекло или не хватает: 1" in reason

    def test_истекающее_жёлтое(self) -> None:
        light, reason = evaluate_direction(DirectionCounts(required=3, expiring=1))
        assert light is TrafficLight.YELLOW
        assert "истекает" in reason

    def test_всё_действует_зелёное(self) -> None:
        light, reason = evaluate_direction(DirectionCounts(required=3))
        assert light is TrafficLight.GREEN
        assert "3" in reason


class TestWorstLight:
    def test_красное_бьёт_жёлтое(self) -> None:
        rows = build_directions(
            medical=DirectionCounts(required=1, missing=1),
            ppe=DirectionCounts(required=1, expiring=1),
            training_overdue=0,
        )
        assert worst_light(rows) is TrafficLight.RED

    def test_не_измеряется_не_портит_итог(self) -> None:
        rows = build_directions(
            medical=DirectionCounts(required=2),
            ppe=DirectionCounts(required=1),
            training_overdue=0,
        )
        assert worst_light(rows) is TrafficLight.GREEN

    def test_ничего_не_измерено_итог_честный(self) -> None:
        rows = build_directions(
            medical=DirectionCounts(),
            ppe=DirectionCounts(),
            training_overdue=0,
        )
        assert worst_light(rows) is TrafficLight.NOT_MEASURED


class TestTrainingWithoutBaseline:
    def test_просрочка_красит(self) -> None:
        row = training_readiness(3)
        assert row.light is TrafficLight.RED
        assert "3" in row.reason

    def test_без_просрочек_не_зелёный_а_эталон_не_задан(self) -> None:
        row = training_readiness(0)
        assert row.light is TrafficLight.NOT_MEASURED
        assert "не задан" in row.reason


class TestBuildDirections:
    def test_порядок_фиксированный_и_все_восемь(self) -> None:
        rows = build_directions(
            medical=DirectionCounts(required=1),
            ppe=DirectionCounts(),
            training_overdue=0,
        )
        assert [r.discipline for r in rows] == [
            Direction.MEDICAL,
            Direction.PPE,
            Direction.TRAINING,
            Direction.FIRE_SAFETY,
            Direction.INDUSTRIAL_SAFETY,
            Direction.ECOLOGY,
            Direction.CIVIL_DEFENSE,
            Direction.ROAD_SAFETY,
        ]

    def test_дисциплины_без_учёта_несут_причину(self) -> None:
        rows = build_directions(
            medical=DirectionCounts(),
            ppe=DirectionCounts(),
            training_overdue=0,
        )
        unmeasured = [r for r in rows if r.discipline is Direction.ECOLOGY]
        assert unmeasured[0].light is TrafficLight.NOT_MEASURED
        assert "не ведётся" in unmeasured[0].reason


def _person(pid: str = "p1", position: str | None = "pos1") -> SimpleNamespace:
    return SimpleNamespace(id=pid, position_id=position)


def _exam(kind, valid_until: date) -> SimpleNamespace:
    return SimpleNamespace(exam_kind=kind, valid_until=valid_until)


def _issue(
    item: str, *, returned: bool = False, expires: datetime | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        item_name=item,
        returned_at=NOW if returned else None,
        expires_at=expires,
    )


def _ppe_norm(item: str, quantity: int = 1) -> SimpleNamespace:
    return SimpleNamespace(item_name=item, quantity=quantity)


class TestMedicalCounts:
    def test_нет_записи_вовсе_это_missing(self) -> None:
        counts = _medical_counts(
            [_person()], {"pos1": {"periodic"}}, {}, today=TODAY, horizon=HORIZON
        )
        assert (counts.required, counts.missing, counts.lapsed) == (1, 1, 0)

    def test_истёкший_экзамен_это_lapsed_а_не_missing(self) -> None:
        exams = {"p1": [_exam("periodic", TODAY - timedelta(days=1))]}
        counts = _medical_counts(
            [_person()], {"pos1": {"periodic"}}, exams, today=TODAY, horizon=HORIZON
        )
        assert (counts.missing, counts.lapsed) == (0, 1)

    def test_экзамен_без_вида_закрывает_любую_норму(self) -> None:
        exams = {"p1": [_exam(None, TODAY + timedelta(days=200))]}
        counts = _medical_counts(
            [_person()], {"pos1": {"periodic"}}, exams, today=TODAY, horizon=HORIZON
        )
        assert (counts.missing, counts.lapsed, counts.expiring) == (0, 0, 0)

    def test_чужой_вид_норму_не_закрывает(self) -> None:
        exams = {"p1": [_exam("preliminary", TODAY + timedelta(days=200))]}
        counts = _medical_counts(
            [_person()], {"pos1": {"periodic"}}, exams, today=TODAY, horizon=HORIZON
        )
        assert counts.missing == 1

    def test_действующий_но_истекающий_это_expiring(self) -> None:
        exams = {"p1": [_exam("periodic", TODAY + timedelta(days=10))]}
        counts = _medical_counts(
            [_person()], {"pos1": {"periodic"}}, exams, today=TODAY, horizon=HORIZON
        )
        assert (counts.missing, counts.lapsed, counts.expiring) == (0, 0, 1)

    def test_сотрудник_без_должности_в_эталон_не_входит(self) -> None:
        counts = _medical_counts(
            [_person(position=None)],
            {"pos1": {"periodic"}},
            {},
            today=TODAY,
            horizon=HORIZON,
        )
        assert counts.required == 0


class TestPpeCounts:
    def test_нет_выдачи_вовсе_это_missing(self) -> None:
        counts = _ppe_counts(
            [_person()],
            {"pos1": [_ppe_norm("Каска")]},
            {},
            now=NOW,
            horizon=HORIZON,
        )
        assert (counts.required, counts.missing) == (1, 1)

    def test_выдано_меньше_нормы_это_lapsed(self) -> None:
        issues = {"p1": [_issue("Перчатки")]}
        counts = _ppe_counts(
            [_person()],
            {"pos1": [_ppe_norm("Перчатки", quantity=2)]},
            issues,
            now=NOW,
            horizon=HORIZON,
        )
        assert (counts.missing, counts.lapsed) == (0, 1)

    def test_возвращённая_выдача_норму_не_закрывает(self) -> None:
        issues = {"p1": [_issue("Каска", returned=True)]}
        counts = _ppe_counts(
            [_person()],
            {"pos1": [_ppe_norm("Каска")]},
            issues,
            now=NOW,
            horizon=HORIZON,
        )
        assert counts.lapsed == 1

    def test_имя_сравнивается_без_регистра(self) -> None:
        issues = {"p1": [_issue("каска ")]}
        counts = _ppe_counts(
            [_person()],
            {"pos1": [_ppe_norm("Каска")]},
            issues,
            now=NOW,
            horizon=HORIZON,
        )
        assert (counts.missing, counts.lapsed) == (0, 0)

    def test_наивная_дата_из_sqlite_не_роняет_подсчёт(self) -> None:
        naive = datetime(2026, 8, 20, 12, 0)  # без зоны — как отдаёт SQLite
        issues = {"p1": [_issue("Каска", expires=naive)]}
        counts = _ppe_counts(
            [_person()],
            {"pos1": [_ppe_norm("Каска")]},
            issues,
            now=NOW,
            horizon=HORIZON,
        )
        assert counts.expiring == 1
