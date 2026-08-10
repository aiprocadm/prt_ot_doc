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


_MODULE_GATE = re.compile(r"is_module_enabled\(\s*[^,]+,\s*[^,]+,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")

#: Гейты на коды ВНЕ реестра, принятые осознанно. Каждая запись — долг с
#: причиной, а не исключение «чтобы гард молчал».
_KNOWN_UNREGISTERED = {
    # OPS-71: импорт-фреймворк гейтится флагом `imports`, которого нет ни в
    # каталоге, ни в тарифах. Значит включить модуль через консоль НЕЛЬЗЯ —
    # строку выдачи некому создать. Отнести его к тарифу или к ядру —
    # коммерческое решение владельца, поэтому здесь долг, а не тихий обход.
    "imports",
}


def _module_gate_codes() -> set[str]:
    """Коды, на которые реально поставлен модульный гейт.

    Разбор точный (ищем именно вызов ``is_module_enabled``), поэтому по нему
    можно проверять ОБРАТНОЕ направление: гейт без записи в реестре.
    """

    codes: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        if path.name == "feature_flags.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "is_module_enabled" not in text:
            continue
        for name in _MODULE_GATE.findall(text):
            match = re.search(rf"^{name}\s*=\s*[\"']([a-z_]+)[\"']", text, re.MULTILINE)
            if match:
                codes.add(match.group(1))
    return codes


def _registered_codes() -> set[str]:
    from app.modules.subscription.registry import MODULE_REGISTRY

    return {module.code for module in MODULE_REGISTRY}


def _catalog_dependencies() -> dict[str, object]:
    """Зависимости между модулями, если их когда-нибудь введут."""

    from app.modules.subscription import plans

    return {
        name: getattr(plans, name) for name in dir(plans) if name.isupper() and "DEPEND" in name
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

    # Обратное направление (BIZ-61 срез-2): гейт на код, которого нет в
    # реестре. Такой модуль не попадёт ни в тариф, ни в консоль — включить его
    # будет нечем, и обнаружится это по жалобе заказчика.
    unregistered = sorted(_module_gate_codes() - _registered_codes() - _KNOWN_UNREGISTERED)
    if unregistered:
        errors.append(
            "гейт поставлен на модуль вне реестра "
            f"({unregistered}) — его нельзя выдать через консоль и он не входит "
            "ни в один тариф; добавьте модуль в app/modules/subscription/registry.py"
        )

    stale_debt = sorted(_KNOWN_UNREGISTERED & _registered_codes())
    if stale_debt:
        errors.append(
            f"коды {stale_debt} уже в реестре — уберите их из _KNOWN_UNREGISTERED, "
            "иначе список долгов начнёт врать"
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
        "у каждого есть backend-гейт; гейтов вне реестра нет "
        f"(принятый долг: {sorted(_KNOWN_UNREGISTERED)}); зависимостей между модулями нет."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
