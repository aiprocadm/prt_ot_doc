"""SEC-64.2 — песочница тяжёлого парсинга/конвертации (rlimits + group-kill).

Тесты гоняют НАСТОЯЩИЕ подпроцессы: смысл песочницы — поведение ОС-лимитов,
мок здесь проверял бы сам себя. POSIX-only тесты помечены skipif: на Windows
песочница честно деградирует до обычного запуска с таймаутом.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core.parse_sandbox import run_sandboxed

_POSIX = os.name == "posix"
posix_only = pytest.mark.skipif(not _POSIX, reason="rlimits/killpg — POSIX-only")


def test_ok_command_returns_completed_process():
    result = run_sandboxed(
        [sys.executable, "-c", "print('ok')"],
        timeout_s=30,
        max_memory_mb=512,
        max_cpu_s=30,
        max_output_mb=16,
    )
    assert result.returncode == 0
    assert b"ok" in result.stdout


def test_failing_command_raises_called_process_error():
    with pytest.raises(subprocess.CalledProcessError):
        run_sandboxed(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            timeout_s=30,
            max_memory_mb=512,
            max_cpu_s=30,
            max_output_mb=16,
        )


@posix_only
def test_timeout_kills_the_whole_process_group(tmp_path: Path):
    """Убит должен быть и внук: soffice порождает детей, и убийство одного
    родителя оставляло бы конвертер жить после «таймаута»."""

    pid_file = tmp_path / "grandchild.pid"
    child_code = (
        "import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(120)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_sandboxed(
            [sys.executable, "-c", child_code],
            timeout_s=2,
            max_memory_mb=512,
            max_cpu_s=60,
            max_output_mb=16,
        )
    # даём ОС мгновение на доставку SIGKILL группе
    deadline = time.monotonic() + 5
    grandchild = int(pid_file.read_text())
    while time.monotonic() < deadline:
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(grandchild, 9)  # не оставляем сироту после провала теста
        pytest.fail("внук пережил таймаут песочницы")


@posix_only
def test_memory_limit_stops_allocation():
    """Злонамеренный файл, раздувающий память конвертера, не должен ронять хост."""

    with pytest.raises(subprocess.CalledProcessError):
        run_sandboxed(
            [sys.executable, "-c", "x = bytearray(300 * 1024 * 1024)"],
            timeout_s=30,
            max_memory_mb=128,
            max_cpu_s=30,
            max_output_mb=16,
        )


@posix_only
def test_output_size_limit_stops_disk_bomb(tmp_path: Path):
    target = tmp_path / "bomb.bin"
    code = f"open({str(target)!r}, 'wb').write(b'x' * (8 * 1024 * 1024))"
    with pytest.raises(subprocess.CalledProcessError):
        run_sandboxed(
            [sys.executable, "-c", code],
            timeout_s=30,
            max_memory_mb=512,
            max_cpu_s=30,
            max_output_mb=1,
        )


@posix_only
def test_cpu_limit_kills_spin_loop():
    """Вечный цикл гибнет по CPU-лимиту, не дожидаясь настенного таймаута."""

    started = time.monotonic()
    with pytest.raises(subprocess.CalledProcessError):
        run_sandboxed(
            [sys.executable, "-c", "while True: pass"],
            timeout_s=30,
            max_memory_mb=512,
            max_cpu_s=1,
            max_output_mb=16,
        )
    assert time.monotonic() - started < 15
