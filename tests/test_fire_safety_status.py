"""ПБ в светофоре дисциплин — по срокам объекта (BIZ-54-57 срез-82, разд. 54.1).

До среза строка «Пожарная безопасность» на карточке площадки всегда говорила
«учёт не ведётся», хотя у площадки есть свои сроки — перезарядка и поверка
средств защиты (срез-79), тренировки и документы (срез-80), — и сводка модуля
ПБ уже считала их по всему арендатору. Здесь закрепляется решение 5 из
``core/discipline_status``:

- просроченный срок объекта красит красным — как истёкшее удостоверение
  красит БДД; в расшифровке названо, что именно просрочено;
- срок в горизонте — жёлтым, с горизонтом в днях;
- порядок в сроках НЕ красит зелёным: что объекту положено, платформа не
  судит, и цвет остаётся «не измеряется» с фактом;
- средства без записи о работах и давность тренировки — факты, не цвет;
- без средств, тренировок и документов — причина словаря, слово в слово;
- кто сроки объекта не считал, получает прежнюю строку, а не нули.

Срез-83 (решение 6): противопожарные инструктажи людей площадки — тоже в
цвет: истёкший — красный наравне с огнетушителем, истекающий — жёлтый,
действующий — факт в расшифровке; зелёного по-прежнему нет, потому что
сколько людям положено инструктажей, платформа не судит.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.discipline_status import (
    FIRE_SAFETY_PERSON_REASON,
    DisciplineCounts,
    FireSafetyNumbers,
    TrafficLight,
    build_discipline_statuses,
    fire_safety_status,
)
from app.core.disciplines import UNMEASURED_DISCIPLINES, Discipline

BASE = UNMEASURED_DISCIPLINES[Discipline.FIRE_SAFETY]


class TestЦвет:
    def test_без_объектов_прежняя_причина(self) -> None:
        row = fire_safety_status(FireSafetyNumbers())
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == BASE
        assert row.counts == DisciplineCounts()

    def test_просрочка_красит_красным_и_названа_по_видам(self) -> None:
        row = fire_safety_status(
            FireSafetyNumbers(
                units=4,
                overdue_recharge=1,
                overdue_inspection=2,
                overdue_documents=1,
                without_maintenance=3,
                documents=2,
            )
        )
        assert row.light is TrafficLight.RED
        assert row.reason == (
            "Просрочено по ПБ — перезарядка средств защиты: 1, поверка/ТО: 2, "
            "пересмотр документов: 1; средств без записи о работах: 3; "
            "проведённых тренировок нет"
        )
        assert row.counts == DisciplineCounts(required=4, lapsed=4)

    def test_тренировка_не_проведена_к_дате_это_просрочка(self) -> None:
        row = fire_safety_status(
            FireSafetyNumbers(
                overdue_drills=1,
                last_drill_on=date(2026, 3, 1),
                days_since_last_drill=188,
            )
        )
        assert row.light is TrafficLight.RED
        assert row.reason == (
            "Просрочено по ПБ — тренировки: 1; последняя тренировка 01.03.2026 (188 дн. назад)"
        )

    def test_скоро_жёлтое_с_горизонтом(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(units=2, due_soon=1, due_soon_days=30))
        assert row.light is TrafficLight.YELLOW
        assert row.reason == (
            "Истекает по ПБ в ближайшие 30 дн. — перезарядка или поверка средств "
            "защиты: 1; проведённых тренировок нет"
        )
        assert row.counts == DisciplineCounts(required=2, expiring=1)

    def test_истёкший_инструктаж_красит_красным_как_огнетушитель(self) -> None:
        """Решение 6 (срез-83): поимённый срок ПБ — в цвет, как удостоверение у БДД."""

        row = fire_safety_status(
            FireSafetyNumbers(overdue_briefings=2, briefings_due_soon=1, briefings_valid=3)
        )
        assert row.light is TrafficLight.RED
        assert row.reason == (
            "Просрочено по ПБ — противопожарные инструктажи: 2; "
            "проведённых тренировок нет; противопожарных инструктажей действует: 3"
        )
        # инструктажи — тоже «положено/просрочено/истекает», как удостоверения
        assert row.counts == DisciplineCounts(required=6, lapsed=2, expiring=1)

    def test_истекающий_инструктаж_жёлтый_рядом_со_средствами(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(units=1, due_soon=1, briefings_due_soon=2))
        assert row.light is TrafficLight.YELLOW
        assert row.reason == (
            "Истекает по ПБ в ближайшие 30 дн. — перезарядка или поверка средств "
            "защиты: 1, противопожарные инструктажи: 2; проведённых тренировок нет"
        )
        assert row.counts == DisciplineCounts(required=3, expiring=3)

    def test_только_действующие_инструктажи_это_объект_но_не_зелёный(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(briefings_valid=5))
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason.startswith("Сроки ПБ не просрочены (средств защиты: 0, документов: 0); ")
        assert "противопожарных инструктажей действует: 5" in row.reason
        assert row.reason.endswith(BASE)

    def test_порядок_в_сроках_не_зелёный_а_факт_с_причиной(self) -> None:
        row = fire_safety_status(
            FireSafetyNumbers(
                units=5,
                documents=3,
                planned_drills=1,
                last_drill_on=date(2026, 8, 20),
                days_since_last_drill=16,
            )
        )
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == (
            "Сроки ПБ не просрочены (средств защиты: 5, документов: 3); "
            f"последняя тренировка 20.08.2026 (16 дн. назад); тренировок назначено: 1. {BASE}"
        )
        assert row.counts == DisciplineCounts(required=5)

    def test_без_записи_о_работах_факт_а_не_цвет(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(units=2, without_maintenance=2))
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason.startswith(
            "Сроки ПБ не просрочены (средств защиты: 2, документов: 0); "
            "средств без записи о работах: 2; "
        )

    def test_только_проведённая_тренировка_это_объект(self) -> None:
        """Проведённая тренировка — факт про площадку: причина уже не «пусто»."""

        row = fire_safety_status(
            FireSafetyNumbers(last_drill_on=date(2026, 9, 1), days_since_last_drill=4)
        )
        assert row.light is TrafficLight.NOT_MEASURED
        assert "последняя тренировка 01.09.2026 (4 дн. назад)" in row.reason
        assert row.reason.endswith(BASE)

    @pytest.mark.parametrize(
        "numbers",
        [
            FireSafetyNumbers(),
            FireSafetyNumbers(units=3),
            FireSafetyNumbers(units=3, due_soon=1),
            FireSafetyNumbers(units=3, overdue_recharge=1),
            FireSafetyNumbers(documents=2, planned_drills=1, last_drill_on=date(2026, 9, 1)),
            FireSafetyNumbers(briefings_valid=7),
            FireSafetyNumbers(units=2, briefings_due_soon=1),
        ],
    )
    def test_пб_никогда_не_зелёная(self, numbers: FireSafetyNumbers) -> None:
        """Сторож решений 5 и 6: сроки объекта и инструктажи — факт, не эталон."""

        assert fire_safety_status(numbers).light is not TrafficLight.GREEN

    def test_просрочка_это_четыре_слагаемых_центра_внимания_плюс_инструктажи(self) -> None:
        numbers = FireSafetyNumbers(
            overdue_recharge=1,
            overdue_inspection=2,
            overdue_drills=3,
            overdue_documents=4,
            overdue_briefings=5,
        )
        assert numbers.overdue == 15
        assert FireSafetyNumbers(due_soon=1, briefings_due_soon=2).expiring == 3


class TestОдинЧеловек:
    """Срез-84 (решение 7): у человека объектов нет — только его инструктажи."""

    def test_без_инструктажей_причина_про_человека_а_не_про_объект(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(objects_counted=False))
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == FIRE_SAFETY_PERSON_REASON
        assert "объект" not in row.reason

    def test_действующие_инструктажи_факт_без_слова_о_тренировках(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(briefings_valid=2, objects_counted=False))
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == (
            f"Противопожарных инструктажей действует: 2. {FIRE_SAFETY_PERSON_REASON}"
        )
        assert row.counts == DisciplineCounts(required=2)

    def test_истёкший_инструктаж_красный_без_слова_о_тренировках(self) -> None:
        row = fire_safety_status(
            FireSafetyNumbers(overdue_briefings=1, briefings_valid=1, objects_counted=False)
        )
        assert row.light is TrafficLight.RED
        assert row.reason == (
            "Просрочено по ПБ — противопожарные инструктажи: 1; "
            "противопожарных инструктажей действует: 1"
        )
        assert row.counts == DisciplineCounts(required=2, lapsed=1)

    def test_истекающий_инструктаж_жёлтый(self) -> None:
        row = fire_safety_status(FireSafetyNumbers(briefings_due_soon=1, objects_counted=False))
        assert row.light is TrafficLight.YELLOW
        assert row.reason == "Истекает по ПБ в ближайшие 30 дн. — противопожарные инструктажи: 1"

    @pytest.mark.parametrize(
        "numbers",
        [
            FireSafetyNumbers(objects_counted=False),
            FireSafetyNumbers(briefings_valid=9, objects_counted=False),
        ],
    )
    def test_у_человека_пб_тоже_не_зелёная(self, numbers: FireSafetyNumbers) -> None:
        assert fire_safety_status(numbers).light is not TrafficLight.GREEN


class TestВСветофоре:
    def _rows(self, **kwargs):
        return build_discipline_statuses(
            medical=DisciplineCounts(), ppe=DisciplineCounts(), training_overdue=0, **kwargs
        )

    def test_без_чисел_прежняя_строка(self) -> None:
        row = next(r for r in self._rows() if r.discipline is Discipline.FIRE_SAFETY)
        assert row.light is TrafficLight.NOT_MEASURED
        assert row.reason == BASE

    def test_с_числами_строка_на_том_же_месте(self) -> None:
        rows = self._rows(fire_safety=FireSafetyNumbers(units=1, overdue_recharge=1))
        assert [r.discipline for r in rows] == list(Discipline)
        fire = next(r for r in rows if r.discipline is Discipline.FIRE_SAFETY)
        assert fire.light is TrafficLight.RED
