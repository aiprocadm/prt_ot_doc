#!/usr/bin/env python3
"""SEC-67: перешифровать хранимые секреты на активный ключ (разд. 67.2 «ротация»).

Ротация без простоя состоит из трёх шагов, и это второй:

1. добавить новый ключ в связку рядом со старым и указать
   ``APP_SECRET_ENCRYPTION_ACTIVE_KID`` — новые записи идут на новый ключ, старые
   продолжают читаться старым;
2. **этот скрипт** — перешифровать существующие строки на активный ключ;
3. убедиться, что на отставной ключ никто не ссылается (``--check``), и убрать его
   из связки.

Шаг 3 нельзя делать раньше шага 2: значение помнит свой ``kid``, и удаление ключа
из связки превратит его в нечитаемое (``decrypt_secret`` падает намеренно —
молчаливый возврат шифротекста дал бы подписи, которые не проверит ни один
подписчик).

Обрабатываются все таблицы с секретами вебхуков; список — :data:`SECRET_COLUMNS`.
Идёт по всем активным арендаторам на bypass-сессии (кросс-тенантная операция).

Использование::

    PYTHONPATH=backend python scripts/rotate_secret_keys.py --check   # только отчёт
    PYTHONPATH=backend python scripts/rotate_secret_keys.py           # перешифровать
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter

# (модель, атрибут с секретом) — всё, что лежит в enc:-конверте.
SECRET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("app.models.models:WebhookEndpoint", "secret"),
    ("app.models.tenant_billing:WebhookSubscription", "secret"),
)


def _load(path: str):
    module_name, _, attr = path.partition(":")
    module = __import__(module_name, fromlist=[attr])
    return getattr(module, attr)


async def _rotate(*, apply: bool) -> tuple[Counter, int]:
    from sqlalchemy import select

    from app.core.secret_cipher import active_key_id, key_id_of, reencrypt_secret
    from app.db.session import AsyncSessionLocal

    active = active_key_id()
    stats: Counter = Counter()
    rewritten = 0

    # rls_bypass: ротация — доверенная кросс-тенантная операция, иначе политики
    # SEC-65 спрячут строки всех арендаторов, кроме контекста сессии.
    async with AsyncSessionLocal(tenant="public", rls_bypass=True) as session:
        for model_path, column in SECRET_COLUMNS:
            model = _load(model_path)
            rows = (await session.execute(select(model))).scalars().all()
            for row in rows:
                stored = getattr(row, column, None)
                if stored is None:
                    continue
                kid = key_id_of(stored)
                label = kid or "plaintext"
                stats[f"{model.__tablename__}:{label}"] += 1
                if kid == active:
                    continue
                if not apply:
                    continue
                setattr(row, column, reencrypt_secret(stored))
                rewritten += 1
        if apply and rewritten:
            await session.commit()
    return stats, rewritten


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="только отчёт: сколько секретов на каком ключе (ничего не пишет)",
    )
    args = parser.parse_args(argv)

    from app.core.secret_cipher import SecretKeyringError, active_key_id

    try:
        active = active_key_id()
    except SecretKeyringError as exc:
        print(f"FAIL: связка ключей не готова: {exc}", file=sys.stderr)
        return 1

    stats, rewritten = asyncio.run(_rotate(apply=not args.check))

    print(f"активный ключ: {active}")
    if not stats:
        print("секретов не найдено — нечего ротировать")
        return 0
    for label in sorted(stats):
        print(f"  {label}: {stats[label]}")

    stale = sum(
        count
        for label, count in stats.items()
        # plaintext тоже подлежит переводу в конверт
        if not label.endswith(f":{active}")
    )
    if args.check:
        if stale:
            print(f"\nтребуют перешифровки: {stale} — запустите без --check")
            return 1
        print("\nвсё на активном ключе: отставной ключ можно убрать из связки")
        return 0

    print(f"\nперешифровано: {rewritten}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI helper
    sys.exit(main())
