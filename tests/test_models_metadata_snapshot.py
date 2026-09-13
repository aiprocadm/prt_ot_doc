"""Сторож: модели собираются, имена экспортируются, схема сверяется (срез-172).

ЧТО БЫЛО. У моделей есть гейт `scripts/ci/check_models_metadata.py`: он
проверяет три вещи — что все связи между моделями разрешаются, что каждое имя
из списка экспорта действительно доступно, и что отпечаток схемы совпадает со
снимком. Гоняли его только из CI, а CI выключен вручную с 13.08. Гейт был
КРАСНЫМ с 16.07: снимок отстал на 71 новую таблицу и 25 снесённых, плюс
восемь имён, удалённых вместе со старыми моделями.

Про это даже писали владельцу в августе («месяц не ловит дрейф схемы»), и с
тех пор ничего не изменилось: проверка есть, выполнять её некому. Тот же
класс, что срезы 170 и 171.

ПОЧЕМУ ВАЖНО. Первые две проверки — постоянные правила, а не разовые: если
связь между моделями не разрешается, приложение падает при первом же запросе;
если имя из списка экспорта исчезло, ломается любой импорт по этому имени.
Третья (отпечаток схемы) — сигнал «схема изменилась»: она не заменяет
миграции, но заставляет изменение заметить.

КАК ОБНОВЛЯТЬ СНИМОК ОСОЗНАННО:
``PYTHONPATH=backend python scripts/ci/check_models_metadata.py --snapshot``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_models_metadata.py"
BASELINE = REPO_ROOT / "docs" / "stabilization" / "models_metadata_baseline.json"


@pytest.fixture(scope="module")
def collected() -> dict:
    spec = importlib.util.spec_from_file_location("check_models_metadata", SCRIPT)
    assert spec and spec.loader, "скрипт сверки моделей не читается"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # _collect зовёт configure_mappers(): неразрешённая связь упадёт здесь.
    return module._collect()


def test_связи_между_моделями_разрешаются(collected: dict) -> None:
    """Постоянное правило: сборка мапперов проходит.

    Проверка выполнена самим сбором; здесь закрепляем, что он вообще случился
    и вернул непустую схему.
    """

    assert len(collected["tables"]) > 200, "схема собралась подозрительно маленькой"


def test_каждое_имя_из_списка_экспорта_доступно() -> None:
    """Постоянное правило, не зависящее от снимка."""

    import app.db.base  # noqa: F401 — подтягивает все модели
    import app.models as models_pkg
    import app.models.models as models_mod

    broken: list[str] = []
    for module in (models_pkg, models_mod):
        for name in getattr(module, "__all__", []):
            if not hasattr(module, name):
                broken.append(f"{module.__name__}.{name}")

    assert not broken, (
        "имя объявлено в списке экспорта, но не существует — импорт по нему "
        "упадёт: " + ", ".join(broken)
    )


def test_отпечаток_схемы_совпадает_со_снимком(collected: dict) -> None:
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = collected["tables"]
    stored = base["tables"]

    added = sorted(set(current) - set(stored))
    removed = sorted(set(stored) - set(current))
    changed = sorted(name for name in set(current) & set(stored) if current[name] != stored[name])

    assert not (added or removed or changed), (
        "схема моделей разошлась со снимком. Это не заменяет миграции, но "
        "изменение надо заметить и снять снимок осознанно:\n"
        + "".join(f"  появилась таблица: {name}\n" for name in added)
        + "".join(f"  пропала таблица:   {name}\n" for name in removed)
        + "".join(f"  изменилась:        {name}\n" for name in changed)
        + "Если изменение задумано: PYTHONPATH=backend python "
        "scripts/ci/check_models_metadata.py --snapshot"
    )


def test_сборка_для_миграций_видит_все_таблицы() -> None:
    """Срез-172: главное правило этого файла, и раньше оно нарушалось.

    `app/db/base.py` — тот список таблиц, по которому alembic сравнивает модели
    с базой. Шесть модулей импортировались НИЖЕ строки сборки, а два не
    импортировались вовсе: в сборке было 262 таблицы из 297, и автогенерация
    миграции предложила бы УДАЛИТЬ 35 живых таблиц.

    Проверка идёт в ОТДЕЛЬНОМ процессе, и это не придирка: в общем прогоне
    соседние тесты успевают импортировать модели раньше, порядок строк внутри
    `base.py` перестаёт играть роль, и подложенная поломка остаётся зелёной.
    Мерить надо ровно то, что видит alembic — свежий интерпретатор, в котором
    импортирован только сам сборщик.
    """

    code = (
        "import app.db.base as base\n"
        "from app.db.session import SharedBase, TenantBase\n"
        "declared = set(SharedBase.metadata.tables) | set(TenantBase.metadata.tables)\n"
        "missing = sorted(declared - set(base.ALEMBIC_METADATA.tables))\n"
        "print('MISSING:' + ','.join(missing))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=600,
    )
    assert result.returncode == 0, f"сборщик метаданных не импортируется:\n{result.stderr[-2000:]}"

    line = next((row for row in result.stdout.splitlines() if row.startswith("MISSING:")), None)
    assert line is not None, f"проверка не дала ответа:\n{result.stdout[-2000:]}"
    missing = [name for name in line[len("MISSING:") :].split(",") if name]

    assert not missing, (
        "таблица объявлена моделью, но не попала в сборку для миграций — "
        "автогенерация предложит её удалить: " + ", ".join(missing)
    )
