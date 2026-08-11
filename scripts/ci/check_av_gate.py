#!/usr/bin/env python3
"""SEC-64 (разд. 64.2): антивирус в конвейере загрузок — обязательный gate.

ТЗ формулирует прямо: «ClamAV в upload pipeline (заявлено — подтвердить как
**обязательный gate**, а не опцию)». Опция, выключенная по умолчанию, gate'ом не
является: развёртывание, забывшее переменную, принимает файлы вообще без проверки,
и заметить это можно только по отсутствию записей сканера.

Гард отвечает на два вопроса:

1. в конфигурации production/staging антивирус включён (``AV_ENABLED=true``)?
2. при включённом антивирусе задан адрес clamd?

На development/test (и когда ``APP_ENV`` не задан) — пропуск: локальная разработка
и набор тестов идут с симулятором по имени файла, поднимать clamd ради них незачем.

Usage::

    APP_ENV=production PYTHONPATH=backend python scripts/ci/check_av_gate.py
"""

from __future__ import annotations

import os
import sys

ENFORCED_ENVIRONMENTS = ("production", "staging")


def main(argv: list[str] | None = None) -> int:
    del argv

    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    if app_env not in ENFORCED_ENVIRONMENTS:
        print(
            f"SKIP: APP_ENV={app_env or '(не задан)'} — gate применяется только к "
            f"{'/'.join(ENFORCED_ENVIRONMENTS)}"
        )
        return 0

    av_enabled = (os.getenv("AV_ENABLED") or "false").strip().lower() in {"1", "true", "yes"}
    if not av_enabled:
        print(
            "FAIL: AV_ENABLED=false в "
            f"{app_env}. Разд. 64.2 требует антивирус как ОБЯЗАТЕЛЬНЫЙ gate: с "
            "выключенным сканером загруженные файлы проходят без проверки, и это "
            "не видно ниоткуда, кроме отсутствия записей сканера.",
            file=sys.stderr,
        )
        return 1

    host = (os.getenv("CLAMAV_HOST") or "").strip()
    unix_socket = (os.getenv("CLAMAV_UNIX_SOCKET") or "").strip()
    if not host and not unix_socket:
        print(
            "FAIL: AV_ENABLED=true, но не задан ни CLAMAV_HOST, ни CLAMAV_UNIX_SOCKET — "
            "сканер недостижим, и каждая проверка вернёт ошибку.",
            file=sys.stderr,
        )
        return 1

    target = unix_socket or f"{host}:{os.getenv('CLAMAV_PORT') or 3310}"
    print(f"OK: антивирус включён в {app_env}, сканер {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
