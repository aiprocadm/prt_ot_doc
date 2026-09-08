"""Contract: после декомпозиции монолита имя модуля остаётся ``app.tasks``."""

from __future__ import annotations


def test_import_app_tasks_resolves_package_with_core_symbols() -> None:
    import app.tasks as tasks

    assert hasattr(tasks, "_run_coroutine")
    assert hasattr(tasks, "generate_document_task")
    assert hasattr(tasks, "RETRYABLE_EXCEPTIONS")
    assert hasattr(tasks, "celery_app")


def test_мёртвый_сканер_правил_напоминаний_не_воскрешён() -> None:
    """Срез-113: ``reminders.scan`` удалён — сторож против возврата вслепую.

    Задача ежечасно обходила арендаторов и читала ``ReminderRule``, а создать
    правило было нельзя ничем: ни ручкой, ни сидом, ни миграцией с данными.
    Механизм выглядел работающим, но всегда находил ноль правил, и рядом жил
    настоящий: библиотека правил дисциплин, события сроков и ежедневная
    ``tasks.reminders.dispatch``.

    Если механизм понадобится — возвращать его надо ВМЕСТЕ с ручками создания
    правил; тогда этот тест обновляют осознанно, а не «чтобы позеленел».
    """

    import app.tasks as tasks
    from app.services.celery_app import celery_app

    assert "reminders.scan" not in celery_app.tasks
    assert "reminders-scan-hourly" not in celery_app.conf.beat_schedule
    assert not hasattr(tasks, "scan_reminders_job")
    # Живой механизм на месте: ежедневная рассылка напоминаний по задачам.
    assert "tasks.reminders.dispatch" in celery_app.tasks
    assert "tasks-reminders-daily" in celery_app.conf.beat_schedule
