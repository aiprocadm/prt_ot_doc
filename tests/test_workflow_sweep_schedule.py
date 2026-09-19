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

КАК ПРОВЕРЯЛОСЬ И ЧТО ИЗМЕНИЛОСЬ (срез-231). Сторож брал задачи, чьё ИМЯ
оканчивается на ``.tick``. Дефект нашёлся ровно за этой границей: уборка ключей
идемпотентности (``idempotency.cleanup``) написана, срок хранения настроен
(``IDEMPOTENCY_TTL_DAYS``), а в расписании её не было и не звал её никто —
единственный путь удаления записей не выполнялся ни разу. Имя не кончается на
``.tick``, поэтому проверка её не видела.

**Область обзора теперь задаётся устройством задачи, а не её именем.** Задача,
которая НЕ ПРИНИМАЕТ АРГУМЕНТОВ, работает сама по себе: позвать её из кода
нечем и незачем, значит запускать её должно расписание. Такая задача обязана
быть либо в расписании, либо в реестре исключений — с причиной у каждой строки.

Это третий раз подряд, когда дефект прятался в области обзора проверки, а не в
её утверждениях (срезы 223, 224, 226).
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
    # --- срез-231: задачи без аргументов, которые запускает не расписание ---
    "outbox.dispatch_all": (
        "включается настройкой `OUTBOX_DISPATCH_SCHEDULE_ENABLED` и тогда "
        "попадает в расписание сама; по умолчанию выключена осознанно — у "
        "существующего развёртывания может лежать накопленная очередь, и первый "
        "же тик отправил бы её подписчикам целиком"
    ),
    "dispatch_outbox_events": (
        "разгрузка очереди ОДНОГО арендатора; по всем обходит " "`outbox.dispatch_all`"
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


def _self_contained_tasks() -> dict[str, str]:
    """Задачи, которые НЕ ПРИНИМАЮТ АРГУМЕНТОВ: имя → модуль объявления.

    Такую задачу неоткуда позвать осмысленно из кода — ей нечего передать.
    Значит, запускать её должно расписание. Признак берётся у самой задачи, а
    не у её имени: имя врёт (срез-231, `idempotency.cleanup`).
    """

    import inspect

    import app.celery.tasks  # noqa: F401
    import app.tasks  # noqa: F401
    from app.services.celery_app import celery_app

    result: dict[str, str] = {}
    for name, task in celery_app.tasks.items():
        if name.startswith("celery."):
            continue
        func = getattr(task, "run", task)
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):  # pragma: no cover - встроенные
            continue
        required = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]
        if not required:
            result[name] = str(getattr(task, "__module__", "?"))
    return result


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


def test_задача_без_аргументов_кем_то_запускается(
    celery_state: tuple[set[str], set[str]],
) -> None:
    """Срез-231. Область обзора — устройство задачи, а не её имя.

    Прежняя проверка брала только имена на ``.tick``, и уборка ключей
    идемпотентности пряталась ровно за этой границей: написана, настроена и не
    запускалась никогда.
    """

    _registered, scheduled = celery_state
    self_contained = _self_contained_tasks()
    assert (
        len(self_contained) > 10
    ), f"задач без аргументов найдено всего {len(self_contained)} — проверка потеряла область"

    orphans = sorted(set(self_contained) - scheduled - set(KNOWN_NOT_SCHEDULED))
    assert not orphans, (
        "задача не принимает аргументов, значит запускать её должно расписание — "
        "а её там нет и не зовёт никто:\n"
        + "\n".join(f"  {name}  ({self_contained[name]})" for name in orphans)
    )


def test_уборка_ключей_идемпотентности_стоит_в_расписании(
    celery_state: tuple[set[str], set[str]],
) -> None:
    """Срез-231: единственный путь удаления записей — эта задача."""

    _registered, scheduled = celery_state
    assert "idempotency.cleanup" in scheduled, (
        "уборка ключей идемпотентности исчезла из расписания — записи снова "
        "начнут копиться вечно, а настроенный срок хранения ничего не значит"
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
