"""БДД в светофоре дисциплин — по удостоверениям водителей (BIZ-54-57 срез-64).

До среза строка «БДД» на карточке сотрудника и площадки всегда говорила
«эталон не ведётся», хотя у допущенного водителя есть один поимённый срок —
удостоверение, и он уже был в общем календаре (``road_safety_driver``).
Здесь закрепляется решение 4 из ``core/discipline_status``:

- истекшее удостоверение красит красным — как просрочка обучения;
- истекающее — жёлтым, с датой;
- действующее НЕ красит зелёным: «всё положенное по БДД действует» из одного
  удостоверения не следует, и цвет остаётся «не измеряется» с фактом;
- без водителей — прежняя причина словаря, слово в слово;
- кто удостоверения не считал, получает прежнюю строку, а не нули.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.discipline_status import (
    DisciplineCounts,
    RoadSafetyNumbers,
    TrafficLight,
    build_discipline_statuses,
    road_safety_status,
)
from app.core.disciplines import UNMEASURED_DISCIPLINES, Discipline

BASE = UNMEASURED_DISCIPLINES[Discipline.ROAD_SAFETY]


class TestЦвет:
    def test_без_водителей_прежняя_причина(self) -> None:
        row = road_safety_status(RoadSafetyNumbers())
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == BASE
        assert row.counts == DisciplineCounts()

    def test_истекшее_красит_красным(self) -> None:
        row = road_safety_status(RoadSafetyNumbers(drivers=2, expired=1, without_due=1))
        assert row.light is TrafficLight.RED
        assert row.reason == "Истекло водительское удостоверение: 1; срок не указан: 1"
        assert row.counts == DisciplineCounts(required=2, lapsed=1)

    def test_истекающее_жёлтое_с_датой(self) -> None:
        row = road_safety_status(
            RoadSafetyNumbers(drivers=1, expiring=1, next_due=date(2026, 9, 20))
        )
        assert row.light is TrafficLight.YELLOW
        assert (
            row.reason == "Водительское удостоверение истекает в ближайшее время: 1 (до 20.09.2026)"
        )
        assert row.counts == DisciplineCounts(required=1, expiring=1)

    def test_действующее_не_зелёное_а_факт_с_причиной(self) -> None:
        row = road_safety_status(RoadSafetyNumbers(drivers=1, next_due=date(2027, 3, 1)))
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == f"Водительское удостоверение действует (до 01.03.2027). {BASE}"

    def test_несколько_действующих_числом(self) -> None:
        row = road_safety_status(
            RoadSafetyNumbers(drivers=3, without_due=1, next_due=date(2027, 3, 1))
        )
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason.startswith("Водительские удостоверения действуют: 2; срок не указан: 1. ")

    def test_только_без_срока_это_сведений_нет_а_не_просрочка(self) -> None:
        row = road_safety_status(RoadSafetyNumbers(drivers=1, without_due=1))
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == f"Срок водительского удостоверения не указан: 1. {BASE}"

    @pytest.mark.parametrize(
        "numbers",
        [
            RoadSafetyNumbers(),
            RoadSafetyNumbers(drivers=1, next_due=date(2030, 1, 1)),
            RoadSafetyNumbers(drivers=5, expiring=2, next_due=date(2026, 9, 10)),
            RoadSafetyNumbers(drivers=5, expired=1, expiring=2),
            RoadSafetyNumbers(drivers=2, without_due=2),
        ],
    )
    def test_бдд_никогда_не_зелёный(self, numbers: RoadSafetyNumbers) -> None:
        """Сторож решения 4: удостоверение — факт, не эталон."""

        assert road_safety_status(numbers).light is not TrafficLight.GREEN


class TestВСветофоре:
    def _rows(self, **kwargs):
        return build_discipline_statuses(
            medical=DisciplineCounts(), ppe=DisciplineCounts(), training_overdue=0, **kwargs
        )

    def test_без_чисел_прежняя_строка(self) -> None:
        row = next(r for r in self._rows() if r.discipline is Discipline.ROAD_SAFETY)
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == BASE

    def test_с_числами_строка_на_том_же_месте(self) -> None:
        rows = self._rows(road_safety=RoadSafetyNumbers(drivers=1, expired=1))
        assert [r.discipline for r in rows] == list(Discipline)
        assert rows[-1].light is TrafficLight.RED
