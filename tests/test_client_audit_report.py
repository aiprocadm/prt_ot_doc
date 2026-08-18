"""BIZ-51 срез-7: сборка отчёта авто-аудита (разд. 51.3).

Правила чистые — проверяются построчно. Закрепляется:

* отчёт всегда отвечает на три вопроса, даже когда ответ «ничего»;
* действия ВЫВОДЯТСЯ из красных направлений и неразобранной ленты, а не
  сочиняются;
* итог отчёта равен худшему измеренному направлению.
"""

from __future__ import annotations

from datetime import date

from app.domains.managed_clients.audit_report import build_report
from app.domains.managed_clients.readiness import DirectionCounts, build_directions

PERIOD = dict(period_start=date(2026, 8, 11), period_end=date(2026, 8, 18))


def _directions(*, medical=None, ppe=None, training_overdue=0):
    return build_directions(
        medical=medical or DirectionCounts(),
        ppe=ppe or DirectionCounts(),
        training_overdue=training_overdue,
    )


class TestBuildReport:
    def test_пустой_период_это_содержание_а_не_молчание(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(medical=DirectionCounts(required=2)),
            changes_by_kind={},
            changes_unhandled=0,
        )
        assert "Изменений за период не зафиксировано" in content.summary
        assert "Разрывов с эталоном не найдено" in content.summary
        assert "Действий не требуется" in content.summary
        assert content.overall == "green"

    def test_изменения_перечислены_по_видам_с_числами(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(),
            changes_by_kind={"Принят новый сотрудник": 2, "Наступает срок": 1},
            changes_unhandled=3,
        )
        assert "Изменений за период: 3" in content.summary
        assert "Принят новый сотрудник — 2" in content.summary
        assert content.payload["changes"]["total"] == 3
        assert content.payload["changes"]["unhandled"] == 3

    def test_действия_выводятся_из_красного_и_неразобранного(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(medical=DirectionCounts(required=3, missing=2)),
            changes_by_kind={},
            changes_unhandled=4,
        )
        assert content.overall == "red"
        actions = content.payload["actions"]
        assert any("Медосмотры" in a and "не оформлено вовсе: 2" in a for a in actions)
        assert any("Разобрать записи ленты изменений: 4" in a for a in actions)
        assert "Что нужно сделать:" in content.summary

    def test_жёлтое_попадает_в_просрочено_но_не_в_действия(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(medical=DirectionCounts(required=3, expiring=1)),
            changes_by_kind={},
            changes_unhandled=0,
        )
        assert content.overall == "yellow"
        assert "Медосмотры" in content.summary
        assert content.payload["actions"] == []

    def test_снимок_несёт_период_и_направления(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(medical=DirectionCounts(required=1)),
            changes_by_kind={},
            changes_unhandled=0,
        )
        assert content.payload["period"] == {"start": "2026-08-11", "end": "2026-08-18"}
        assert len(content.payload["directions"]) == 8
