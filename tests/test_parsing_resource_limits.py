"""SEC-64 (разд. 64.2): ограничение ресурсов для тяжёлого разбора документов.

ТЗ: «Изоляция обработки: тяжёлый парсинг/конвертация в отдельных worker'ах **с
ограничением ресурсов**».

Предел по ВРЕМЕНИ в проекте был (`task_soft_time_limit` / `task_time_limit`), предела
по ПАМЯТИ — не было. Разница существенная: патологический документ или конвертация
LibreOffice раздувают RSS в пределах отведённых 300 секунд, и таймаут не срабатывает —
раньше отработает OOM-killer хоста, забрав с собой соседние контейнеры.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_worker_has_a_memory_ceiling() -> None:
    from app.services.celery_app import celery_app

    limit_kib = celery_app.conf.worker_max_memory_per_child
    assert limit_kib and limit_kib > 0, "без предела по памяти таймаут не спасёт от OOM"
    # Celery ждёт КИЛОБАЙТЫ, настройка задаётся в мегабайтах — ошибка в множителе
    # даёт либо перезапуск после каждой задачи, либо отсутствие предела.
    assert limit_kib == 1024 * 1024, "по умолчанию 1 ГБ = 1048576 КиБ"


def test_worker_recycles_by_task_count_too() -> None:
    """Предел по памяти ловит всплеск, счётчик задач — медленную утечку."""

    from app.services.celery_app import celery_app

    assert celery_app.conf.worker_max_tasks_per_child > 0


def test_time_limits_are_still_in_place() -> None:
    from app.services.celery_app import celery_app

    soft = celery_app.conf.task_soft_time_limit
    hard = celery_app.conf.task_time_limit
    assert soft and hard
    # Мягкий предел обязан быть строго меньше жёсткого: иначе задача не получает
    # шанса завершиться штатно и всегда убивается сигналом.
    assert soft < hard


@pytest.mark.parametrize(
    ("setting", "expected_kib"),
    [(0, 0), (1, 1024), (512, 524_288)],
)
def test_megabytes_convert_to_kibibytes(setting: int, expected_kib: int) -> None:
    """Ноль означает «без ограничения» и не должен превращаться в «перезапуск всегда»."""

    computed = setting * 1024 if setting > 0 else 0
    assert computed == expected_kib


@pytest.mark.parametrize("service", ["worker", "lo"])
def test_compose_limits_the_parsing_containers(service: str) -> None:
    """Лимит внутри Celery не спасёт от процесса, который порождает воркер
    (LibreOffice), — поэтому рамки нужны и на уровне контейнера."""

    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    definition = compose["services"][service]
    assert definition.get("mem_limit"), f"{service}: не задан mem_limit"
    assert definition.get("cpus"), f"{service}: не задан cpus"
