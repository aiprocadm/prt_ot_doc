"""SEC-64 (разд. 64.2): антивирусная проверка загруженных файлов.

ТЗ требует «ClamAV в upload pipeline — подтвердить как **обязательный gate**, а не
опцию». Этого не было: модуль возвращал ``clean`` всему, в чьём ИМЕНИ нет подстроки
``eicar``/``virus``, то есть был симулятором, а не проверкой. Настоящий клиент
ClamAV в проекте существовал (``app/services/clamav.py``), но им пользовался только
легаси-путь ``api/routes/files.py``; новый конвейер (``modules/files``) шёл мимо.

Теперь:

* ``AV_ENABLED=true`` → скан идёт через настоящий clamd (``services/clamav.py``);
* ошибка сканера — это **не** ``clean``. Недоступный clamd раньше означал бы, что
  файл объявлен чистым; теперь возвращается ``error``, и вызывающий код отправляет
  файл в карантин. Fail-closed: непроверенный файл не считается безопасным;
* ``AV_ENABLED=false`` → прежний симулятор по имени, чтобы локальная разработка и
  тесты работали без поднятого clamd. Выключенный антивирус в production/staging
  ловит отдельная проверка ``scripts/ci/check_av_gate.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["AVResult", "scan_file"]


@dataclass
class AVResult:
    status: str
    signature: str | None = None


def _simulated(path: Path) -> AVResult:
    """Проверка по имени для dev/test: EICAR-файл «заражён», остальное чисто."""

    name = path.name.lower()
    if "eicar" in name or "virus" in name:
        return AVResult(status="infected", signature="simulated.eicar")
    return AVResult(status="clean")


def scan_file(path: Path, *, settings=None) -> AVResult:
    """Просканировать файл. Возвращает ``clean`` / ``infected`` / ``error``."""

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    if not getattr(settings, "av_enabled", False):
        return _simulated(path)

    from app.services.clamav import ClamAVError, ClamAVVerdict, get_clamav_client

    try:
        with path.open("rb") as stream:
            outcome = get_clamav_client().scan_stream(stream)
    except (ClamAVError, OSError) as exc:
        # Здесь пролегает граница fail-open/fail-closed: вернув "clean", мы объявили
        # бы непроверенный файл безопасным при каждом сбое clamd.
        logger.warning("files.av.scan_failed", extra={"error": str(exc)})
        return AVResult(status="error", signature=None)

    if outcome.status == ClamAVVerdict.INFECTED:
        return AVResult(status="infected", signature=outcome.signature)
    if outcome.status == ClamAVVerdict.CLEAN:
        return AVResult(status="clean")
    logger.warning("files.av.unexpected_verdict", extra={"raw": outcome.raw})
    return AVResult(status="error", signature=outcome.signature)
