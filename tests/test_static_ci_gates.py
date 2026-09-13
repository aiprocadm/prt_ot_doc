"""Сторож: статические гейты выполняются на каждом прогоне (срез-174).

ЧТО БЫЛО. В `scripts/ci/` пятнадцать проверок, и запускали их только из CI, а
CI выключен вручную с 13.08. Проверка, которую никто не выполняет, ничего не
охраняет: срез-171 нашёл так протухший снимок задач, срез-172 — сборку таблиц
для миграций, где автогенерация предложила бы удалить 35 живых таблиц.

Пять проверок не требуют ни базы, ни сети, ни сборки образа, и потому могут
идти вместе с обычными тестами:

* пароли по умолчанию в примерах настроек;
* реестр исключений безопасности (просроченные записи);
* версия Python в описаниях сборки;
* обязательные файлы окружения выполнения;
* запросы без ограничения по арендатору.

Остальные требуют живую базу, npm или отчёт о покрытии — им место в CI, и
сюда они не берутся намеренно.

КАК ЧИТАТЬ ПАДЕНИЕ. Тест печатает вывод самой проверки: там уже написано, что
именно не так. Запустить вручную:
``PYTHONPATH=backend python scripts/ci/<имя>.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATES = [
    "check_default_secrets",
    "check_security_exceptions",
    "check_workflow_python_version",
    "check_runtime_artifacts",
    "check_scoped_queries",
]


def _run_gate(name: str) -> subprocess.CompletedProcess[str]:
    script = REPO_ROOT / "scripts" / "ci" / f"{name}.py"
    assert script.exists(), f"гейт {name} исчез из scripts/ci"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=900,
    )


@pytest.mark.parametrize("gate", GATES)
def test_статический_гейт_зелёный(gate: str) -> None:
    result = _run_gate(gate)
    assert result.returncode == 0, (
        f"гейт {gate} красный. Он не требует ни базы, ни сети, поэтому его "
        f"падение — настоящая находка, а не окружение.\n"
        f"--- вывод ---\n{result.stdout[-3000:]}\n{result.stderr[-2000:]}"
    )


def test_список_гейтов_не_отстал_от_папки() -> None:
    """Новый статический гейт должен попасть сюда, а не остаться без запуска."""

    present = {path.stem for path in (REPO_ROOT / "scripts" / "ci").glob("check_*.py")}
    #: Требуют живую базу, npm, отчёт о покрытии или образ — им место в CI.
    NEEDS_ENVIRONMENT = {
        "check_av_gate",
        "check_backend_coverage_baseline",
        "check_celery_tasks",  # закрыт своим тестом (срез-171)
        "check_context_boundaries",  # закрыт своим тестом
        "check_models_metadata",  # закрыт своим тестом (срез-172)
        "check_module_gates",
        "check_npm_audit",
        "check_openapi_snapshot",  # закрыт своим тестом
        "check_rls_runtime_role",
        "check_scoped_coverage",
    }

    unclaimed = sorted(present - set(GATES) - NEEDS_ENVIRONMENT)
    assert not unclaimed, (
        "в scripts/ci появилась проверка, которую никто не запускает: "
        + ", ".join(unclaimed)
        + ". Либо добавьте её в список этого теста, либо в перечень требующих "
        "окружения — с причиной."
    )
