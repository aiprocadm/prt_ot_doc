"""Model + migration pins for report_definition (P10-07 rb01)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from tests.utils.factories import TestDataFactory

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "backend/app/migrations/versions/20260710_rb01_report_definition.py"
)


def _squash(text: str) -> str:
    # black может переносить аргументы — сравниваем без пробелов/переносов
    return "".join(text.split())


def test_migration_pins() -> None:
    src = MIGRATION.read_text(encoding="utf-8")
    flat = _squash(src)
    assert 'revision="20260710_rb01_report_definition"' in flat
    assert 'down_revision="20260709_med03_psychiatric_342n"' in flat
    assert '"report_definition"' in flat
    assert (
        _squash('sa.UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name")')
        in flat
    )
    assert '"deleted_at"' in flat  # SoftDeleteMixin column present
    assert 'server_default="{}"' in flat  # config_json backfill-safe default
    assert _squash('op.drop_table("report_definition")') in flat  # round-trip


@pytest.mark.asyncio
async def test_model_roundtrip(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.models import ReportDefinition  # re-export обязателен

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        record = ReportDefinition(
            tenant_id=str(tenant.id),
            name="Тестовый отчёт",
            dataset_code="incidents",
            config_json={"columns": ["title"]},
        )
        session.add(record)
        await session.commit()

        row = await session.scalar(
            select(ReportDefinition).where(ReportDefinition.tenant_id == str(tenant.id))
        )
        assert row is not None
        assert row.is_system is False  # ORM default
        assert row.deleted_at is None
        assert row.config_json == {"columns": ["title"]}
