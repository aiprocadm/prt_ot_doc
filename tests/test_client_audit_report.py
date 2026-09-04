"""BIZ-51 срез-7: сборка отчёта авто-аудита (разд. 51.3).

Правила чистые — проверяются построчно. Закрепляется:

* отчёт всегда отвечает на три вопроса, даже когда ответ «ничего»;
* действия ВЫВОДЯТСЯ из красных направлений и неразобранной ленты, а не
  сочиняются;
* итог отчёта равен худшему измеренному направлению;
* происшествия (срез-52) — отдельным числом по дисциплинам и действием
  «довести до закрытия», цвет от них не меняется, неразмеченное названо.
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

    def test_происшествия_по_дисциплинам_названы_и_не_красят_светофор(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(medical=DirectionCounts(required=2)),
            changes_by_kind={},
            changes_unhandled=0,
            incidents_open={"road_safety": 2, "ecology": 1, "fire_safety": 0},
            incidents_unmarked=1,
        )
        # цвет — только от эталона; происшествия его не трогают
        assert content.overall == "green"
        assert (
            "Открытых происшествий: 4 (БДД — 2; Экология — 1; не размечено — 1)." in content.summary
        )
        actions = content.payload["actions"]
        assert "БДД: довести до закрытия 2 происшествия" in actions
        assert "Экология: довести до закрытия 1 происшествие" in actions
        assert "Разметить дисциплиной в реестре происшествий: 1" in actions
        assert not any("Пожарная" in a for a in actions), "ноль — не действие"
        assert content.payload["incidents"] == {
            "total": 4,
            "by_discipline": {"road_safety": 2, "ecology": 1},
            "unmarked": 1,
        }
        by_code = {row["direction"]: row for row in content.payload["directions"]}
        assert by_code["road_safety"]["incidents_open"] == 2
        assert by_code["medical"]["incidents_open"] == 0

    def test_без_происшествий_сказано_словами_а_не_пропущено(self) -> None:
        content = build_report(
            **PERIOD,
            directions=_directions(),
            changes_by_kind={},
            changes_unhandled=0,
        )
        assert "Открытых происшествий нет." in content.summary
        assert content.payload["incidents"] == {"total": 0, "by_discipline": {}, "unmarked": 0}
        assert "Действий не требуется" in content.summary

    def test_дисциплины_вне_редакции_названы_фразой_а_не_пропущены(self) -> None:
        """BIZ-54-57 срез-55, приёмка §58.3: строк меньше, но скрытое не молчит."""

        rows = [
            row
            for row in _directions(medical=DirectionCounts(required=2))
            if row.discipline.value not in ("ecology", "civil_defense")
        ]
        content = build_report(
            **PERIOD,
            directions=rows,
            changes_by_kind={},
            changes_unhandled=0,
            not_applicable=["Экология", "ГО и ЧС"],
        )
        assert (
            "Вне отчёта: Экология, ГО и ЧС — модули у исполнителя не подключены, "
            "статус по ним не считается." in content.summary
        )
        assert {r["direction"] for r in content.payload["directions"]} == {
            "medical",
            "ppe",
            "training",
            "fire_safety",
            "industrial_safety",
            "road_safety",
        }
        assert content.payload["not_applicable"] == ["Экология", "ГО и ЧС"]
        assert content.overall == "green"

    def test_без_скрытого_фразы_нет_и_снимок_несёт_пустой_список(self) -> None:
        content = build_report(
            **PERIOD, directions=_directions(), changes_by_kind={}, changes_unhandled=0
        )
        assert "Вне отчёта" not in content.summary
        assert content.payload["not_applicable"] == []

    def test_происшествие_по_скрытой_дисциплине_не_прячется(self) -> None:
        """Происшествие — факт, редакция исполнителя его не отменяет."""

        rows = [row for row in _directions() if row.discipline.value != "ecology"]
        content = build_report(
            **PERIOD,
            directions=rows,
            changes_by_kind={},
            changes_unhandled=0,
            incidents_open={"ecology": 1},
            not_applicable=["Экология"],
        )
        assert "Открытых происшествий: 1 (Экология — 1)." in content.summary
        assert "Экология: довести до закрытия 1 происшествие" in content.payload["actions"]
