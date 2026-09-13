"""Сторож: обход сроков и таймеров согласований кто-то запускает (срез-170).

ЧТО БЫЛО. Две работы написаны давно и покрыты тестами: ``workflow.sla.tick``
помечает просроченные задачи согласования и пишет событие эскалации,
``workflow.timers.tick`` исполняет созревшие таймеры процесса. Обе принимают
арендатора параметром — и потому НИ ОДНА не попала в расписание: туда берут
только задачи без аргументов. Вызовов из кода тоже не было. Механизм
существовал, а запускать его было некому: сроки согласований не
эскалировались никогда, таймеры не срабатывали никогда.

Это тот же класс, что срез-113 («сканер правил был недостижим») и срез-158
(«событие публиковала не та задача»): код есть, тесты зелёные, в жизни не
происходит ничего.

КАК ПРОВЕРЯЕТСЯ. Берём расписание живого приложения и все зарегистрированные
задачи. Каждая задача, которая по имени объявлена периодической (оканчивается
на ``.tick``), обязана быть либо в расписании, либо в списке тех, кого зовёт
веерная задача. Реестр исключений требует причину у каждой строки.
"""

from __future__ import annotations

import pytest

#: Периодическая по имени задача, которой в расписании нет, и это осознанно.
#: Каждая строка обязана объяснять, кто её запускает вместо расписания.
KNOWN_NOT_SCHEDULED: dict[str, str] = {
    "workflow.sla.tick": (
        "принимает арендатора параметром; по всем арендаторам обходит "
        "`workflow.sweep.tick` (срез-170)"
    ),
    "workflow.timers.tick": (
        "принимает арендатора параметром; по всем арендаторам обходит "
        "`workflow.sweep.tick` (срез-170)"
    ),
}


@pytest.fixture(scope="module")
def celery_state() -> tuple[set[str], set[str]]:
    """(имена зарегистрированных задач, имена задач из расписания)."""

    import app.celery.tasks  # noqa: F401  — регистрация задач
    import app.tasks  # noqa: F401
    from app.services.celery_app import celery_app

    registered = {name for name in celery_app.tasks if not name.startswith("celery.")}
    schedule = celery_app.conf.beat_schedule or {}
    scheduled = {entry.get("task") for entry in schedule.values() if isinstance(entry, dict)}
    return registered, scheduled


def test_расписание_и_задачи_читаются(celery_state: tuple[set[str], set[str]]) -> None:
    registered, scheduled = celery_state
    assert len(registered) > 40, f"задач найдено всего {len(registered)} — модули не подгрузились"
    assert len(scheduled) > 10, f"строк расписания всего {len(scheduled)}"
    assert "tasks.reminders.dispatch" in scheduled


def test_каждая_периодическая_задача_кем_то_запускается(
    celery_state: tuple[set[str], set[str]],
) -> None:
    registered, scheduled = celery_state
    periodic = {name for name in registered if name.endswith(".tick")}
    assert len(periodic) > 5, "периодических задач почти не найдено — проверка потеряла область"

    orphans = sorted(periodic - scheduled - set(KNOWN_NOT_SCHEDULED))
    assert not orphans, (
        "периодическая задача есть, а запускать её некому — в жизни она не "
        "выполнится ни разу:\n" + "\n".join(f"  {name}" for name in orphans)
    )


def test_обход_согласований_стоит_в_расписании(
    celery_state: tuple[set[str], set[str]],
) -> None:
    _registered, scheduled = celery_state
    assert "workflow.sweep.tick" in scheduled, (
        "обход сроков и таймеров согласований исчез из расписания — эскалация "
        "просроченных задач и созревшие таймеры снова перестанут срабатывать"
    )


def test_реестр_исключений_не_протух(celery_state: tuple[set[str], set[str]]) -> None:
    registered, scheduled = celery_state
    for name, reason in KNOWN_NOT_SCHEDULED.items():
        assert reason.strip(), f"у исключения {name} нет причины"
        assert name in registered, f"исключение {name} указывает на несуществующую задачу"
        assert name not in scheduled, f"{name} теперь в расписании — уберите строку из реестра"
