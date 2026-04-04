"""Contract: после декомпозиции монолита имя модуля остаётся ``app.tasks``."""

from __future__ import annotations


def test_import_app_tasks_resolves_package_with_core_symbols() -> None:
    import app.tasks as tasks

    assert hasattr(tasks, "_run_coroutine")
    assert hasattr(tasks, "generate_document_task")
    assert hasattr(tasks, "RETRYABLE_EXCEPTIONS")
    assert hasattr(tasks, "celery_app")
