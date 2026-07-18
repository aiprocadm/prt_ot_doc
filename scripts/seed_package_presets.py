from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.models import ClientPackagePreset, Tenant

PRESETS = [
    {
        "code": "OUT_TO_SITE",
        "name": "Выход на объект",
        "description": "Пакет для выхода на объект",
        "required_inputs_json": [
            {"key": "workers", "title": "Список работников", "type": "table"},
            {"key": "permits", "title": "Допуски", "type": "file"},
            {"key": "ppe", "title": "СИЗ", "type": "table"},
        ],
    },
    {
        "code": "INCIDENT",
        "name": "Несчастный случай",
        "description": "Пакет документов по НС",
        "required_inputs_json": [
            {"key": "committee", "title": "Состав комиссии", "type": "table"},
            {"key": "acts", "title": "Акты", "type": "file"},
        ],
    },
    {
        "code": "INSPECTION_PREP",
        "name": "Подготовка к проверке",
        "description": "Пакет подготовки к проверке",
        "required_inputs_json": [
            {"key": "checklists", "title": "Чек-листы", "type": "file"},
            {"key": "evidence", "title": "Доказательства", "type": "file"},
        ],
    },
]


async def main() -> None:
    async with AsyncSessionLocal(tenant="public") as public_session:
        tenants = (await public_session.execute(select(Tenant.slug))).scalars().all()

    for tenant_slug in tenants:
        async with AsyncSessionLocal(tenant=tenant_slug) as session:
            for payload in PRESETS:
                exists = (
                    await session.execute(
                        select(ClientPackagePreset).where(
                            ClientPackagePreset.code == payload["code"]
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                session.add(
                    ClientPackagePreset(
                        code=payload["code"],
                        name=payload["name"],
                        description=payload["description"],
                        steps_json={"pipeline": ["template", "headers", "replace", "pdf", "zip"]},
                        required_inputs_json=payload["required_inputs_json"],
                        is_active=True,
                    )
                )
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
