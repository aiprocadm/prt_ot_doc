#!/usr/bin/env python3
"""SEC-69: выгрузить полную спецификацию OpenAPI в файл — вход для DAST.

ZAP умеет обходить API по спецификации (`-f openapi`), и это единственный
осмысленный способ сканировать JSON-API: обычный «паук» ходит по ссылкам в HTML,
которых у нас нет.

Спецификацию берём из объекта приложения, а не с живой ручки ``/api/openapi.json``:

* ручка доступна не во всех режимах запуска (в production документация отключена
  намеренно, в dockerless-режиме её тоже нет);
* она требует заголовок ``X-Tenant``, то есть скан пришлось бы настраивать на
  аутентификацию раньше, чем он получит список эндпоинтов;
* прямой вызов ``app.openapi()`` даёт ПОЛНЫЙ набор путей независимо от того, что
  сервер решил показывать снаружи.

Usage::

    PYTHONPATH=backend python scripts/ci/dump_openapi.py --output openapi.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openapi.json",
        help="куда записать спецификацию (по умолчанию ./openapi.json)",
    )
    args = parser.parse_args(argv)

    # Приложение требует минимальный набор секретов даже для сборки схемы.
    for key, value in (
        ("SECRET_KEY", "dast-openapi-dump"),
        ("S3_ACCESS_KEY", "dast-openapi-dump"),
        ("S3_SECRET_KEY", "dast-openapi-dump"),
    ):
        os.environ.setdefault(key, value)

    from app.api.app import create_app

    spec = create_app().openapi()
    paths = spec.get("paths") or {}
    if not paths:
        print("FAIL: спецификация без путей — сканировать нечего", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    operations = sum(
        1
        for methods in paths.values()
        for method in methods
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    )
    print(f"OK: {output} — {len(paths)} путей, {operations} операций")
    return 0


if __name__ == "__main__":
    sys.exit(main())
