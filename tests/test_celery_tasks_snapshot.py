"""Сторож: снимок списка задач сверяется на каждом прогоне (срез-171).

ЧТО БЫЛО. Снимок имён задач (`docs/stabilization/celery_tasks_baseline.json`)
заведён, чтобы переименование задачи не сломало молча расписание и вызовы по
имени. Сверяет его отдельный скрипт, а запускали его только из CI — а CI
выключен вручную с 13.08. В итоге снимок протух: в нём не было ПЯТИ задач,
добавленных прежними волнами, и оставалась одна снятая. Проверка существовала,
но её никто не выполнял — тот же класс, что и сама находка среза-170.

ПОЧЕМУ ЭТО ВАЖНО. Расписание и вызовы по имени связаны с задачей только
строкой. Переименовали задачу — расписание молча указывает в пустоту, и никто
не падает: работа просто перестаёт выполняться. Снимок — единственное место,
где такое видно.

КАК ПРОВЕРЯЕТСЯ. Тест зовёт ту же сверку, что и скрипт, и падает на любом
расхождении. Обновлять снимок нужно ОСОЗНАННО:
``PYTHONPATH=backend python scripts/ci/check_celery_tasks.py --snapshot``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_celery_tasks.py"
BASELINE = REPO_ROOT / "docs" / "stabilization" / "celery_tasks_baseline.json"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_celery_tasks", SCRIPT)
    assert spec and spec.loader, "скрипт сверки задач не читается"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _in_scope(task: object) -> bool:
    """Задача объявлена в пакете ``app.tasks``.

    Проверять началом строки нельзя: рядом лежит модуль `app.tasks_replace`
    (без точки), и он в область снимка не входит — сверка на нём спотыкалась.
    """

    module = str(getattr(task, "__module__", ""))
    return module == "app.tasks" or module.startswith("app.tasks.")


def _names_outside_scope() -> set[str]:
    """Имена из снимка, объявленные вне ``app.tasks`` (их регистрирует другой пакет)."""

    from app.services.celery_app import celery_app

    return {name for name, task in celery_app.tasks.items() if not _in_scope(task)}


def test_снимок_на_месте_и_не_пуст() -> None:
    assert BASELINE.exists(), "снимок списка задач исчез"
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert len(data["task_names"]) > 30, "в снимке подозрительно мало задач"


def _names_in_scope_of_snapshot() -> set[str]:
    """Имена задач из области снимка — тех, что регистрирует ``app.tasks``.

    В прогоне тестов реестр задач общий на процесс, и соседние тесты успевают
    подтянуть ещё один пакет задач (`app.celery.tasks`, проекции). Скрипт
    сверки запускается в одиночку и их не видит, поэтому сравнивать «всё, что
    в реестре» нельзя — иначе тест ругался бы на чужое. Область задаём по
    модулю, в котором задача объявлена.
    """

    import app.tasks  # noqa: F401 — регистрация задач
    from app.services.celery_app import celery_app

    return {
        name
        for name, task in celery_app.tasks.items()
        if not name.startswith("celery.") and _in_scope(task)
    }


def test_список_задач_совпадает_со_снимком(checker) -> None:
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    current_names = _names_in_scope_of_snapshot()
    base_names = {
        name
        for name in base["task_names"]
        if name in current_names or name not in _names_outside_scope()
    }

    added = sorted(current_names - set(base["task_names"]))
    removed = sorted(base_names - current_names)

    assert not (added or removed), (
        "список задач разошёлся со снимком. Переименование задачи молча рвёт "
        "расписание и вызовы по имени, поэтому обновлять снимок надо осознанно:\n"
        + "".join(f"  появилось: {name}\n" for name in added)
        + "".join(f"  пропало:   {name}\n" for name in removed)
        + "Если изменение задумано: PYTHONPATH=backend python "
        "scripts/ci/check_celery_tasks.py --snapshot"
    )


def test_в_снимке_есть_обход_согласований() -> None:
    """Срез-170 добавил его; строка-образец держит область проверки."""

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert "workflow.sweep.tick" in base["task_names"]
