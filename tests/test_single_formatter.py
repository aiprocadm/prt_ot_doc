"""Один форматтер, и он в гейте (срез-218).

ЧТО БЫЛО. Форматтеров было два — ``black`` и ``ruff format`` — и ни один не был
чист: ``black --check`` (шаг ``make lint``) был красным на 170 файлах, ``ruff
format --check`` расходился на 195. ``black`` при этом не стоял ни в одном
настоящем гейте (``local_gate.py``, ``static_gates.sh``), а держал две записи в
``.github/security-exceptions.yml`` со сроком 30.09.2026 — то есть подъём до
``black`` 26 означал бы переформатирование всего кода ради инструмента,
который ничего не проверял.

РЕШЕНИЕ. ``black`` убран, форматтер один — ``ruff format`` — и он проверяется в
``make lint``. Этот сторож не даёт второму форматтеру вернуться и держит
``ruff format --check`` зелёным на путях линта.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LINT_PATHS = ("backend/app", "tests", "scripts")

#: Файлы, где второй форматтер мог бы прописаться снова.
_CONFIG_FILES = (
    "Makefile",
    "requirements-dev.txt",
    ".pre-commit-config.yaml",
    "pyproject.toml",
)


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_второго_форматтера_нет() -> None:
    """``black`` не должен вернуться ни в зависимости, ни в гейт, ни в хуки."""

    for rel in _CONFIG_FILES:
        text = _text(rel)
        # Комментарии, объясняющие, ПОЧЕМУ black убран, — не возврат black.
        code_lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        assert not re.search(r"\bblack\b", "\n".join(code_lines)), f"{rel}: black вернулся"


def test_линт_проверяет_формат() -> None:
    """Форматтер обязан стоять в ``make lint`` — иначе он снова никого не держит."""

    makefile = _text("Makefile")
    lint_block = makefile.split("lint:", 1)[1].split("\n\n", 1)[0]
    assert "format --check" in lint_block, "make lint не проверяет ruff format"


def test_исключения_black_сняты() -> None:
    """Записи-исключения для убранного пакета не должны висеть до срока."""

    text = _text(".github/security-exceptions.yml")
    assert "PYSEC-2026-2120" not in text and "PYSEC-2026-2121" not in text


def test_код_отформатирован_ruff() -> None:
    """Живая проверка: ``ruff format --check`` на путях линта зелёная."""

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", *LINT_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-500:]
