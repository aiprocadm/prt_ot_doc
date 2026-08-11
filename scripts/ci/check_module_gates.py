#!/usr/bin/env python3
"""SEC-63 (разд. 63.3): модульный доступ как поверхность атаки — ратчет-гард.

ТЗ называет три риска модульного доступа. Этот гард закрывает два из них
статически, до запуска:

1. **«Обход через прямой API: выключенный на фронте модуль доступен по прямому
   вызову»** → каждый код из ``FEATURE_CATALOG`` обязан встречаться в вызове
   ``is_feature_enabled`` на бэкенде. Сейчас закрыты все восемь модулей, но ничто
   не мешало добавить девятый и забыть гейт — тогда «отключённый» модуль остаётся
   доступным всем, у кого есть токен, и заметить это можно только пентестом.

2. **«Эскалация через зависимости: включение модуля-зависимости открывает больше,
   чем ожидалось»** → у текущего каталога зависимостей нет, и риск неприменим.
   Гард падает, если зависимости появятся: тогда решение об их обработке нужно
   принять осознанно, а не унаследовать молчанием.

Третий риск разд. 63.3 («осиротевшие доступы») статикой не проверяется — см.
``docs/security/MODULE_ENTITLEMENTS.md``.

Чисто статический разбор исходников: база не нужна, гард идёт в обычном наборе CI.

Usage::

    PYTHONPATH=backend python scripts/ci/check_module_gates.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend" / "app"

# Код модуля обычно лежит в константе (`_FEATURE_CODE = "budget"`), поэтому ищем
# и прямые строки, и присваивания константам — иначе гард требовал бы инлайнить
# литерал в вызов и толкал к худшему коду.
_CODE_LITERAL = re.compile(r"""["']([a-z_]+)["']""")


def _catalog() -> dict[str, str]:
    from app.modules.subscription.plans import FEATURE_CATALOG

    return dict(FEATURE_CATALOG)


def _gated_codes() -> set[str]:
    """Коды модулей, встречающиеся в файлах, где вызывается is_feature_enabled."""

    codes: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        if path.name == "feature_flags.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "is_feature_enabled" not in text:
            continue
        codes.update(_CODE_LITERAL.findall(text))
    return codes


def _catalog_dependencies() -> dict[str, object]:
    """Зависимости между модулями, если их когда-нибудь введут."""

    from app.modules.subscription import plans

    return {
        name: getattr(plans, name)
        for name in dir(plans)
        if name.isupper() and "DEPEND" in name
    }


def main(argv: list[str] | None = None) -> int:
    del argv

    catalog = _catalog()
    gated = _gated_codes()

    errors: list[str] = []

    missing = sorted(code for code in catalog if code not in gated)
    if missing:
        errors.append(
            "модули каталога без backend-гейта (is_feature_enabled) — выключённый "
            f"модуль остался бы доступен по прямому вызову API: {missing}"
        )

    dependencies = _catalog_dependencies()
    if dependencies:
        errors.append(
            "в каталоге появились зависимости между модулями "
            f"({sorted(dependencies)}) — разд. 63.3 требует убедиться, что включение "
            "зависимости не открывает больше ожидаемого; обработайте это явно и "
            "обновите гард"
        )

    if errors:
        print("Module entitlements guard FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        f"Module entitlements guard passed: {len(catalog)} модулей каталога, "
        "у каждого есть backend-гейт; зависимостей между модулями нет."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
