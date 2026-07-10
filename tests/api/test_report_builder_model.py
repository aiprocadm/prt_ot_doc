"""Model + migration pins for report_definition (P10-07 rb01)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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


@pytest.mark.asyncio
async def test_name_unique_including_soft_deleted(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """uq_report_definition_tenant_name действует БЕЗ фильтра deleted_at:
    soft-deleted тёзка не освобождает слот (паттерн PPESupplier, честный 409)."""
    from app.models.models import ReportDefinition

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # rollback() ниже экспирит все объекты сессии; ленивое чтение
        # tenant.id после него — sync IO → MissingGreenlet. Кэшируем заранее.
        tenant_id = str(tenant.id)
        first = ReportDefinition(
            tenant_id=tenant_id,
            name="Дубль",
            dataset_code="incidents",
            config_json={},
        )
        session.add(first)
        await session.commit()

        session.add(
            ReportDefinition(
                tenant_id=tenant_id,
                name="Дубль",
                dataset_code="risks",
                config_json={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        first.deleted_at = datetime.now(tz=timezone.utc)
        session.add(first)
        await session.commit()

        session.add(
            ReportDefinition(
                tenant_id=tenant_id,
                name="Дубль",
                dataset_code="risks",
                config_json={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
