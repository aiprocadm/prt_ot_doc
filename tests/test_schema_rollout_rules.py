"""OPS-74, разд. 74.2: правила раската схемы по всем арендаторам.

ТЗ: «миграция должна безопасно и **отслеживаемо** пройти по всем, **с прогрессом
и возможностью паузы**».

До этого среза умели обновить ОДНОГО арендатора по имени. На тридцати клиентах
это ещё «запустить тридцать раз», на трёхстах — уже нет: непонятно, где
остановились, нельзя приостановить на пике нагрузки и нельзя продолжить с места
после обрыва.

Здесь закрепляются РЕШЕНИЯ, а не вёрстка отчёта:

1. **продолжение с места** — уже сделанные не повторяются;
2. **устойчивый порядок** — два запуска сравнимы, «встали на таком-то» значит
   одно и то же место;
3. **прогресс называет ИМЯ** — «17 из 300» без имени не подскажет, на ком встал
   раскат;
4. **ошибка одного не держит остальных**, но названа поимённо: счётчик
   «с ошибкой: 3» не говорит, к кому идти.
"""

from __future__ import annotations

from app.ops.schema_rollout import (
    RolloutOutcome,
    format_progress,
    plan_rollout,
    summarize,
)


def test_уже_сделанные_не_повторяются() -> None:
    """ГЛАВНОЕ для продолжения: раскат идёт с места обрыва, а не сначала."""

    todo = plan_rollout(["beta", "acme", "gamma"], already_done={"acme"})

    assert todo == ["beta", "gamma"]


def test_порядок_устойчивый() -> None:
    """Случайный порядок сделал бы отчёты двух запусков несравнимыми."""

    assert plan_rollout(["gamma", "acme", "beta"], set()) == ["acme", "beta", "gamma"]
    assert plan_rollout(["beta", "gamma", "acme"], set()) == ["acme", "beta", "gamma"]


def test_пустые_имена_отбрасываются() -> None:
    assert plan_rollout(["acme", "", "beta"], set()) == ["acme", "beta"]


def test_прогресс_называет_имя_и_долю() -> None:
    line = format_progress(17, 300, "acme")

    assert "17/300" in line
    assert "acme" in line, "прогресс без имени не подскажет, на ком встал раскат"
    assert "5%" in line


def test_прогресс_не_делит_на_ноль() -> None:
    assert "100%" in format_progress(0, 0, "никого")


def test_итог_разделяет_сделанное_пропущенное_и_ошибки() -> None:
    summary = summarize(
        [
            RolloutOutcome("acme", "done"),
            RolloutOutcome("beta", "skipped"),
            RolloutOutcome("gamma", "failed", "нет места на диске"),
        ]
    )

    assert summary.done == ["acme"]
    assert summary.skipped == ["beta"]
    assert summary.failed == [("gamma", "нет места на диске")]
    assert summary.is_clean is False


def test_ошибки_названы_поимённо() -> None:
    """Счётчик «с ошибкой: 3» не говорит, к кому идти разбираться."""

    lines = summarize([RolloutOutcome("gamma", "failed", "нет места")]).as_lines()

    assert any("gamma" in line and "нет места" in line for line in lines)


def test_чистый_раскат_виден_сразу() -> None:
    summary = summarize([RolloutOutcome("acme", "done"), RolloutOutcome("beta", "done")])

    assert summary.is_clean is True
    assert "обновлено: 2" in summary.as_lines()[0]
