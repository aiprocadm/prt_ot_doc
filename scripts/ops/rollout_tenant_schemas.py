#!/usr/bin/env python3
"""OPS-74, разд. 74.2: раскатать схему по ВСЕМ арендаторам — с прогрессом и паузой.

ТЗ: «Миграция по всем схемам арендаторов: schema-per-tenant означает N схем;
миграция должна безопасно и отслеживаемо пройти по всем, с прогрессом и
возможностью паузы».

ЧТО БЫЛО. Умели обновлять ОДНОГО арендатора по имени
(``scripts/migrate_tenant.py``). На тридцати клиентах это «запустить тридцать
раз», на трёхстах — уже нет: непонятно, где остановились, нельзя приостановить
на пике нагрузки и нельзя продолжить с места после обрыва.

ЗАПУСК::

    PYTHONPATH=backend python scripts/ops/rollout_tenant_schemas.py --dry-run
    PYTHONPATH=backend python scripts/ops/rollout_tenant_schemas.py

ПАУЗА. Создайте файл-флаг (по умолчанию ``.rollout-pause`` в корне репозитория)
— раскат остановится ПОСЛЕ текущего арендатора и скажет, на ком встал. Удалите
файл и запустите снова: продолжит с места, потому что сделанные записаны в
журнал (``.rollout-state.json``).

ПОЧЕМУ ПАУЗА МЕЖДУ АРЕНДАТОРАМИ, А НЕ ВНУТРИ. Остановка посреди одного оставила
бы его схему на полпути — состояние, из которого потом никто не знает, как
выходить.

ЧТО ДЕЛАЕТ ШАГ. Идемпотентную довыкатку схемы арендатора (та же операция, что и
при заведении клиента): создаёт недостающие таблицы, ничего не удаляет.
ГРАНИЦА НАЗВАНА: изменение СУЩЕСТВУЮЩИХ таблиц — это alembic по общей схеме, он
запускается отдельно; здесь — доведение схем арендаторов до текущего состава.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal, aensure_tenant_schema  # noqa: E402
from app.models.models import Tenant  # noqa: E402
from app.ops.schema_rollout import (  # noqa: E402
    RolloutOutcome,
    format_progress,
    plan_rollout,
    summarize,
)

DEFAULT_STATE = REPO_ROOT / ".rollout-state.json"
DEFAULT_PAUSE = REPO_ROOT / ".rollout-pause"


async def _all_tenants() -> list[tuple[str, str]]:
    """Все арендаторы: (слаг, имя схемы). Читается без арендатора — это работа платформы."""

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = (await session.execute(select(Tenant.slug, Tenant.schema_name))).all()
    return [(row.slug, row.schema_name or f"tenant_{row.slug}") for row in rows if row.slug]


def _load_done(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()
    try:
        return set(json.loads(state_path.read_text(encoding="utf-8")).get("done", []))
    except (OSError, ValueError):
        # Испорченный журнал — это «начинаем заново», а не падение: раскат
        # идемпотентен, повтор безопаснее отказа.
        return set()


def _save_done(state_path: Path, done: set[str]) -> None:
    state_path.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False), encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="показать план, ничего не менять")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="журнал сделанных")
    parser.add_argument("--pause-flag", type=Path, default=DEFAULT_PAUSE, help="файл-флаг паузы")
    parser.add_argument("--restart", action="store_true", help="начать заново, забыв журнал")
    args = parser.parse_args()

    tenants = await _all_tenants()
    schema_by_slug = dict(tenants)
    done = set() if args.restart else _load_done(args.state)
    todo = plan_rollout([slug for slug, _ in tenants], done)

    print(f"всего арендаторов: {len(tenants)}; уже сделано: {len(done)}; предстоит: {len(todo)}")
    if args.dry_run:
        for position, slug in enumerate(todo, start=1):
            print(format_progress(position, len(todo), slug))
        print("сухой прогон: ничего не менялось")
        return 0

    outcomes: list[RolloutOutcome] = []
    for position, slug in enumerate(todo, start=1):
        print(format_progress(position, len(todo), slug), flush=True)
        try:
            await aensure_tenant_schema(slug, schema_name=schema_by_slug[slug])
            outcomes.append(RolloutOutcome(slug=slug, status="done"))
            done.add(slug)
            _save_done(args.state, done)
        except Exception as exc:  # noqa: BLE001 - один сломанный не держит остальных
            outcomes.append(RolloutOutcome(slug=slug, status="failed", detail=str(exc)[:200]))
            print(f"  ОШИБКА: {exc}", flush=True)

        # Пауза проверяется ПОСЛЕ завершённого арендатора.
        if args.pause_flag.exists():
            print(f"пауза по файлу {args.pause_flag.name}: остановились после «{slug}»")
            break

    summary = summarize(outcomes)
    for line in summary.as_lines():
        print(line)
    return 0 if summary.is_clean else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
