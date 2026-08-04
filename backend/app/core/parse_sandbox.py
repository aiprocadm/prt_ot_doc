"""SEC-64.2 (разд. 64.2 «Изоляция обработки»): песочница тяжёлых подпроцессов.

Конвертация и тяжёлый парсинг работают над ЧУЖИМИ файлами — файл арендатора
может быть собран так, чтобы раздуть память, занять CPU навсегда или исписать
диск. Обычный ``subprocess.run(timeout=...)`` от этого не защищает, и хуже
того — по таймауту убивает только прямого ребёнка: LibreOffice порождает
собственных детей (oosplash → soffice.bin), и они переживали «таймаут»,
накапливаясь на сервере.

Песочница:

* ``RLIMIT_AS`` — потолок адресного пространства (раздувание памяти гибнет
  внутри подпроцесса, а не OOM-киллером на хосте);
* ``RLIMIT_CPU`` — потолок процессорного времени (вечный цикл не доживает
  до настенного таймаута);
* ``RLIMIT_FSIZE`` — потолок размера записываемого файла (дисковая бомба);
* ``RLIMIT_CORE=0`` — упавший конвертер не оставляет core-дампов с
  содержимым чужого документа;
* ``start_new_session=True`` + ``killpg(SIGKILL)`` по таймауту — умирает
  ВСЯ группа процессов, а не только родитель.

На Windows rlimit'ов нет — песочница честно деградирует до обычного запуска
с таймаутом (dev-среда владельца; серверы — Linux).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess

__all__ = ["run_sandboxed"]

logger = logging.getLogger(__name__)

_POSIX = os.name == "posix"


def _rlimit_applier(*, max_memory_mb: int, max_cpu_s: int, max_output_mb: int):
    """Собрать preexec_fn: выполняется В РЕБЁНКЕ между fork и exec."""

    import resource  # POSIX-only; импорт здесь, чтобы модуль грузился и на Windows

    def _apply() -> None:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (max_memory_mb * 1024 * 1024, max_memory_mb * 1024 * 1024),
        )
        resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_s, max_cpu_s))
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (max_output_mb * 1024 * 1024, max_output_mb * 1024 * 1024),
        )
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return _apply


def run_sandboxed(
    cmd: list[str],
    *,
    timeout_s: int,
    max_memory_mb: int,
    max_cpu_s: int,
    max_output_mb: int,
) -> subprocess.CompletedProcess[bytes]:
    """Запустить команду под ресурсными лимитами; семантика ``check=True``.

    Бросает ``subprocess.CalledProcessError`` при ненулевом коде выхода
    (включая гибель по любому из rlimit'ов) и ``subprocess.TimeoutExpired``
    по настенному таймауту — убив при этом всю группу процессов.
    """

    if not _POSIX:
        return subprocess.run(cmd, timeout=timeout_s, check=True, capture_output=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        preexec_fn=_rlimit_applier(
            max_memory_mb=max_memory_mb,
            max_cpu_s=max_cpu_s,
            max_output_mb=max_output_mb,
        ),
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        logger.warning(
            "parse-sandbox: команда убита по таймауту (вместе с группой)",
            extra={"cmd": cmd[0], "timeout_s": timeout_s},
        )
        raise
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
