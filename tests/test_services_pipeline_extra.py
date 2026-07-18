from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.metrics import PipelineStage, PipelineType, StageResult
from app.core.tenant import tenant_context
from app.db import Base, SharedBase
from app.models.models import (
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.services.file_storage import FileStorageService
from app.services.pipeline import PipelineService


def _prepare_sqlite_metadata() -> None:
    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in Base.metadata.tables:
        Tenant.__table__.tometadata(Base.metadata, schema=None)


@pytest_asyncio.fixture()
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    _prepare_sqlite_metadata()
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _create_tenant(session: AsyncSession, slug: str) -> Tenant:
    tenant = Tenant(slug=slug, name=slug.title(), contact_email=f"{slug}@example.com")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def _create_template(
    session: AsyncSession, tenant: Tenant
) -> tuple[Template, TemplateVersion]:
    template = Template(
        tenant_id=tenant.id,
        name="pipeline",
        description=None,
        metadata_json={},
        storage_key=f"{tenant.slug}/templates/source.docx",
    )
    session.add(template)
    await session.flush()
    version = TemplateVersion(
        tenant_id=tenant.id,
        template_id=template.id,
        version=1,
        checksum=b"checksum",
        status=TemplateVersionStatus.ACTIVE,
        payload_key=f"{tenant.slug}/templates/source.docx",
    )
    session.add(version)
    await session.commit()
    await session.refresh(template)
    await session.refresh(version)
    return template, version


class FakeMetrics:
    def __init__(self) -> None:
        self.pipeline_statuses: list[tuple[str, str]] = []
        self.errors: list[str] = []
        self.pdf_durations: list[tuple[str, float]] = []

    def observe_pipeline_run(self, *, template_id: str, status: str) -> None:
        self.pipeline_statuses.append((template_id, status))

    def record_pipeline_stage_start(
        self,
        *,
        pipeline: PipelineType,
        stage: PipelineStage,
    ) -> None:
        return None

    def record_pipeline_stage_end(
        self,
        *,
        pipeline: PipelineType,
        stage: PipelineStage,
        result: StageResult,
        seconds: float,
        error_class: str | None = None,
    ) -> None:
        if result is StageResult.FAILED and error_class:
            self.errors.append(error_class)

    def record_pipeline_error(
        self,
        *,
        pipeline: PipelineType,
        stage: PipelineStage,
        error_class: str,
    ) -> None:
        self.errors.append(error_class)

    def observe_pipeline_total_duration(
        self,
        *,
        pipeline: PipelineType,
        seconds: float,
    ) -> None:
        return None

    def increment_pipeline_inflight(self, *, pipeline: PipelineType) -> None:
        return None

    def decrement_pipeline_inflight(self, *, pipeline: PipelineType) -> None:
        return None

    def observe_pdf_duration(self, *, template_id: str, seconds: float) -> None:
        self.pdf_durations.append((template_id, seconds))


class _UnusedPdfConverter:
    def convert(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("PDF conversion must not be invoked in this test")


@pytest.mark.asyncio()
async def test_prepare_parameters_requires_tenant_binding() -> None:
    service = PipelineService(
        storage=FileStorageService(), pdf_converter=_UnusedPdfConverter(), metrics=None
    )
    fake_session = SimpleNamespace(info={})

    template = Template(
        tenant_id="ignored", name="tpl", description=None, metadata_json={}, storage_key="key"
    )
    template.tenant_id = None  # type: ignore[assignment]
    version = TemplateVersion(
        tenant_id="ignored",
        template_id="tpl",
        version=1,
        checksum=b"x",
        status=TemplateVersionStatus.ACTIVE,
        payload_key="payload",
    )

    with pytest.raises(ValueError, match="Template is not bound to a tenant"):
        service._prepare_parameters(  # type: ignore[arg-type]
            session=fake_session,
            template=template,
            template_version=version,
            context={},
            replacements=None,
            header_text=None,
            footer_text=None,
            output_basename=None,
            tenant_id=None,
        )


@pytest.mark.asyncio()
async def test_prepare_parameters_detects_tenant_mismatch() -> None:
    service = PipelineService(
        storage=FileStorageService(), pdf_converter=_UnusedPdfConverter(), metrics=None
    )
    fake_session = SimpleNamespace(info={"tenant": "other", "tenant_id": "other-tenant-id"})

    template = Template(
        tenant_id="tenant-a",
        name="tpl",
        description=None,
        metadata_json={},
        storage_key="key",
    )
    version = TemplateVersion(
        tenant_id="tenant-a",
        template_id="tpl",
        version=1,
        checksum=b"x",
        status=TemplateVersionStatus.ACTIVE,
        payload_key="payload",
    )

    with pytest.raises(ValueError, match="Session tenant does not match"):
        service._prepare_parameters(  # type: ignore[arg-type]
            session=fake_session,
            template=template,
            template_version=version,
            context={},
            replacements=None,
            header_text=None,
            footer_text=None,
            output_basename=None,
            tenant_id="tenant-a",
        )

    version.tenant_id = "tenant-b"  # type: ignore[assignment]
    fake_session.info.clear()
    with pytest.raises(ValueError, match="belongs to a different tenant"):
        service._prepare_parameters(  # type: ignore[arg-type]
            session=fake_session,
            template=template,
            template_version=version,
            context={},
            replacements=None,
            header_text=None,
            footer_text=None,
            output_basename=None,
            tenant_id=None,
        )


@pytest.mark.asyncio()
async def test_normalize_error_details_maps_template_missing() -> None:
    message, code = PipelineService._normalize_error_details(
        RuntimeError("Template version payload missing from storage")
    )
    assert message == "template_version_payload_missing_from_storage"
    assert code == "template_not_uploaded"


@pytest.mark.asyncio()
async def test_ensure_pending_run_detects_request_conflicts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        tenant = await _create_tenant(session, "conflict")
        template, version = await _create_template(session, tenant)
        run = PipelineRun(
            tenant_id=tenant.id,
            template_id=template.id,
            template_version_id=version.id,
            status=PipelineRunStatus.QUEUED,
            context={},
            idempotency_key="dup",
            result_metadata={
                "request": {
                    "replacements": {},
                    "header_text": "alpha",
                    "footer_text": None,
                    "output_basename": None,
                }
            },
        )
        session.add(run)
        await session.commit()

        service = PipelineService(
            storage=FileStorageService(), pdf_converter=_UnusedPdfConverter(), metrics=None
        )
        with pytest.raises(ValueError, match="Idempotency key collision"):
            await service.ensure_pending_run(
                session,
                template=template,
                template_version=version,
                context={},
                replacements={},
                header_text="beta",
                footer_text=None,
                idempotency_key="dup",
                output_basename=None,
            )


@pytest.mark.asyncio()
async def test_get_or_create_pending_run_handles_integrity_race(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        tenant = await _create_tenant(session, "race")
        template, version = await _create_template(session, tenant)
        service = PipelineService(
            storage=FileStorageService(), pdf_converter=_UnusedPdfConverter(), metrics=None
        )
        original_flush = session.flush
        call_counter = {"count": 0}

        async def fake_flush(*args, **kwargs):  # type: ignore[no-untyped-def]
            call_counter["count"] += 1
            if call_counter["count"] == 1:
                async with session_factory() as other:
                    other.add(
                        PipelineRun(
                            tenant_id=tenant.id,
                            template_id=template.id,
                            template_version_id=version.id,
                            status=PipelineRunStatus.QUEUED,
                            context={"foo": "bar"},
                            idempotency_key="race-key",
                        )
                    )
                    await other.commit()
                raise IntegrityError("", "", None)
            return await original_flush(*args, **kwargs)

        session.flush = fake_flush  # type: ignore[assignment]

        run, created = await service._get_or_create_pending_run(
            session,
            tenant_id=tenant.id,
            idempotency_key="race-key",
            template_id=template.id,
            template_version_id=version.id,
            payload={"foo": "bar"},
        )
        assert created is False
        assert run.context == {"foo": "bar"}


@pytest.mark.asyncio()
async def test_run_records_error_when_payload_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        tenant = await _create_tenant(session, "missing")
        template, version = await _create_template(session, tenant)
        version.payload_key = ""  # trigger validation branch
        await session.merge(version)
        await session.commit()
        metrics = FakeMetrics()
        service = PipelineService(
            storage=FileStorageService(), pdf_converter=_UnusedPdfConverter(), metrics=metrics
        )

        with tenant_context(tenant.slug):
            with pytest.raises(RuntimeError, match="Template version payload missing"):
                await service.run(
                    session,
                    template=template,
                    template_version=version,
                    context={},
                    replacements=None,
                    header_text=None,
                    footer_text=None,
                    idempotency_key="error-key",
                    output_basename="report",
                    tenant_id=tenant.id,
                )

        stored = await session.execute(
            select(PipelineRun).where(PipelineRun.idempotency_key == "error-key")
        )
        run = stored.scalar_one()
        assert run.status is PipelineRunStatus.ERROR
        assert run.error == "template_version_payload_missing"
        assert run.result_metadata["error"] == "template_version_payload_missing"
        assert metrics.pipeline_statuses[0][1] == PipelineRunStatus.RUNNING.value
        assert metrics.pipeline_statuses[-1][1] == PipelineRunStatus.ERROR.value
        assert metrics.errors == ["template_not_uploaded"]
