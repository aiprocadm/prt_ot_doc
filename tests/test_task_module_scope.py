"""Сторож: у каждого фонового обхода назван хозяин (SEC-63 разд. 63.3, срез-205).

ЧТО НАШЛА СВЕРКА. Разд. 63.3 называет три вида «осиротевших доступов» после
отключения модуля: **API-ключи, вебхуки и ЗАДАЧИ**. Вебхуки гасились с BIZ-61,
ручки закрыты роутовыми гейтами, а фоновые обходы — нет: они брали ВСЕХ
активных арендаторов и работали, не спрашивая, продан ли модуль.

На живом примере: ``contractors.readiness.tick`` каждую ночь слал уведомления о
готовности подрядчиков и пересобирал витрину арендатору, у которого модуль
«Подрядчики» отключён. Человек получал письмо про раздел, которого не видит и
за который не платит; если модуль отключили по требованию безопасности,
платформа продолжала обрабатывать ровно те данные, обработку которых
прекратили.

ЧТО СТЕРЕЖЁТ ЭТОТ ТЕСТ. У КАЖДОЙ задачи расписания должна быть запись: либо
модуль, либо явное «это ядро» С ПРИЧИНОЙ. Третьего состояния нет. Без этого
новый модульный обход завёлся бы молча и работал у тех, кто модуль не покупал,
а узнали бы об этом по жалобе.

ПОЧЕМУ НЕ ПО ИМЕНИ. Имя задачи похоже на код модуля не всегда: ``ppe.expiry.tick``
выглядит как модуль «СИЗ», но базовые СИЗ — ЯДРО (модуля ``ppe`` в каталоге нет,
есть ``warehouse`` — «Склад СИЗ», другая функция). Угадывание по имени однажды
выключило бы ядровой обход у всех.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_task_module_scope.py -v``.
"""

from __future__ import annotations

import pytest

import app.tasks  # noqa: F401 - регистрирует задачи в Celery
from app.modules.subscription.registry import MODULE_REGISTRY
from app.services.celery_app import celery_app
from app.tasks.module_scope import CORE_TASKS, TASK_MODULE, module_for_task


def _scheduled_tasks() -> set[str]:
    return {entry["task"] for entry in celery_app.conf.beat_schedule.values()}


def _registered_tasks() -> set[str]:
    """ВСЕ задачи, известные Celery, — включая те, что попадают в расписание
    ПО НАСТРОЙКЕ.

    Это различие поймал сам сторож: ``outbox.dispatch_all`` добавляется в
    расписание только при ``OUTBOX_DISPATCH_SCHEDULE_ENABLED``, и сверка со
    списком расписания объявила его «снятой задачей» просто потому, что в
    тестовом окружении настройка выключена.
    """

    return set(celery_app.tasks.keys())


def test_каждая_задача_расписания_описана() -> None:
    """ГЛАВНАЯ ПРОВЕРКА: новая задача не проскочит мимо решения."""

    described = set(TASK_MODULE) | set(CORE_TASKS)
    missing = sorted(_scheduled_tasks() - described)

    assert not missing, (
        "в расписании есть задачи без записи о хозяине:\n  "
        + "\n  ".join(missing)
        + "\nУкажите модуль в TASK_MODULE или объявите ядровой в CORE_TASKS с причиной "
        "(app/tasks/module_scope.py)."
    )


def test_в_реестре_нет_задач_которых_уже_нет_в_расписании() -> None:
    """Иначе реестр копил бы мёртвые записи, и следующий читатель не понял бы,
    какие из них про живые обходы."""

    described = set(TASK_MODULE) | set(CORE_TASKS)
    stale = sorted(described - _registered_tasks())

    assert not stale, f"записи о задачах, которых нет в коде: {stale}"


def test_задача_не_бывает_одновременно_модульной_и_ядровой() -> None:
    assert not set(TASK_MODULE) & set(CORE_TASKS)


def test_коды_модулей_настоящие() -> None:
    """Опечатка в коде модуля означала бы, что обход гасится всегда или
    никогда, — и заметили бы это не тестом, а тишиной в рассылке."""

    known = {module.code for module in MODULE_REGISTRY}
    unknown = sorted(set(TASK_MODULE.values()) - known)

    assert not unknown, f"нет таких модулей в реестре: {unknown}"


def test_у_ядровой_задачи_названа_причина() -> None:
    """«Ядро» без объяснения через полгода читается как «никто не разобрался»."""

    for task, reason in CORE_TASKS.items():
        assert reason.strip(), f"{task}: пустая причина"
        assert len(reason) > 15, f"{task}: причина слишком короткая, чтобы что-то объяснить"


def test_модульные_задачи_ссылаются_на_продаваемые_модули() -> None:
    """Ядровой модуль выключить нельзя, и гасить по нему обход бессмысленно —
    такая запись означала бы, что кто-то перепутал модуль."""

    core_codes = {module.code for module in MODULE_REGISTRY if module.is_core}
    wrong = sorted(code for code in TASK_MODULE.values() if code in core_codes)

    assert not wrong, f"обход привязан к ЯДРОВОМУ модулю (его нельзя отключить): {wrong}"


class TestРазборХозяина:
    def test_модульная_задача_называет_модуль(self) -> None:
        assert module_for_task("contractors.readiness.tick") == "contractors"

    def test_ядровая_задача_не_называет_модуль(self) -> None:
        assert module_for_task("notifications.dispatch_pending") is None

    def test_незнакомая_задача_это_ГРОМКАЯ_ошибка(self) -> None:
        """Молчаливое «наверное, ядро» означало бы, что новый модульный обход
        работает у тех, кто модуль не покупал."""

        with pytest.raises(KeyError) as exc:
            module_for_task("выдуманная.задача.tick")
        assert "module_scope" in str(exc.value)
