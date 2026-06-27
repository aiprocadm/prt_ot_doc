from __future__ import annotations

import logging
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
from app.services.docx import DocxService
from app.services.file_storage import FileStorageService
from app.services.pdf import PdfConversionError, PdfConversionResult
from app.services.pipeline import PipelineService


def _prepare_sqlite_metadata() -> None:
    SharedBase.metadata.schema = None
    for table in SharedBase.metadata.tables.values():
        table.schema = None
    if "tenant" not in Base.metadata.tables:
        Tenant.__table__.tometadata(Base.metadata, schema=None)


class _FakePdfConverter:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def convert(self, input_path: Path, output_dir: Path) -> PdfConversionResult:
        if self.should_fail:
            raise PdfConversionError("pdf_conversion_timeout")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / (input_path.stem + ".pdf")
        output_path.write_bytes(b"%PDF-1.4\n")
        return PdfConversionResult(path=output_path, fallback_used=False, error_code=None)


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    _prepare_sqlite_metadata()
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as seed:
        for slug in {"acme", "beta", "gamma", "delta", "zeta", "epsilon"}:
            seed.add(
                Tenant(
                    slug=slug,
                    name=slug.title(),
                    contact_email=f"{slug}@example.com",
                )
            )
        await seed.commit()
    async with Session() as session:
        yield session
    await engine.dispose()


async def _prepare_template(
    session: AsyncSession, tenant: Tenant
) -> tuple[Template, TemplateVersion]:
    template = Template(tenant_id=tenant.id, name="pipeline", description=None, metadata_json={})
    session.add(template)
    await session.flush()

    storage = FileStorageService.default()
    payload_key = "templates/source.docx"
    storage.put(payload_key, b"template-bytes", content_type=PipelineService.DOCX_CONTENT_TYPE)

    version = TemplateVersion(
        tenant_id=tenant.id,
        template_id=template.id,
        version=1,
        checksum=b"checksum",
        status=TemplateVersionStatus.ACTIVE,
        payload_key=payload_key,
    )
    session.add(version)
    await session.flush()
    return template, version


def _patch_docx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        DocxService,
        "render_template",
        staticmethod(lambda src, context: b"rendered"),
    )
    monkeypatch.setattr(
        DocxService,
        "mass_replace",
        staticmethod(lambda data, repl: data),
    )
    monkeypatch.setattr(
        DocxService,
        "set_headers_footers",
        staticmethod(lambda data, header, footer: data),
    )


@pytest.mark.asyncio()
async def test_pipeline_logs_start_and_success(
    session: AsyncSession, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())

    with tenant_context("acme"):
        with caplog.at_level(logging.INFO):
            run = await service.run(
                session,
                tenant_id=tenant.id,
                template=template,
                template_version=version,
                context={"name": "Jane"},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="job-1",
                output_basename="report",
            )

    start_record = next(r for r in caplog.records if r.message == "Pipeline job started")
    assert start_record.job_id == run.id
    assert start_record.template_id == template.id
    assert start_record.template_version_id == version.id
    assert start_record.tenant == "acme"

    success_record = next(r for r in caplog.records if r.message == "Pipeline job finished")
    assert success_record.job_id == run.id
    assert success_record.pdf_fallback is False
    assert success_record.duration_seconds >= 0
    assert run.tenant_id == tenant.id


@pytest.mark.asyncio()
async def test_pipeline_skips_qr_and_watermark_when_disabled(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())
    service._settings.doc_pipeline_enable_qr = False
    service._settings.doc_pipeline_enable_watermark = False

    with tenant_context("acme"):
        run = await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={"name": "Olga"},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="job-qr-skip",
            output_basename="report",
        )

    stages = run.outputs.get("stages", {})
    assert stages.get("qr_code", {"status": "skipped"})["status"] == "skipped"
    assert stages.get("watermark", {"status": "skipped"})["status"] == "skipped"


@pytest.mark.asyncio()
async def test_pipeline_qr_watermark_failure_fallback(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())
    service._settings.doc_pipeline_enable_qr = True
    service._settings.doc_pipeline_enable_watermark = True

    def _qr(pdf_bytes: bytes, payload: str) -> bytes:
        _ = payload
        return pdf_bytes

    def _watermark(pdf_bytes: bytes, text: str) -> bytes:
        _ = text
        raise RuntimeError("watermark_failed")

    monkeypatch.setattr(service, "_apply_qr_code_to_pdf", _qr)
    monkeypatch.setattr(service, "_apply_watermark_to_pdf", _watermark)

    with tenant_context("beta"):
        run = await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={"name": "Ivan"},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="job-qr-fail",
            output_basename="report",
        )

    assert run.status == PipelineRunStatus.DONE
    stages = run.outputs.get("stages", {})
    assert stages.get("qr_code", {"status": "success"})["status"] == "success"
    assert stages.get("watermark", {"status": "error"})["status"] == "error"


@pytest.mark.asyncio()
async def test_pipeline_logs_pdf_timeout_fallback(
    session: AsyncSession, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter(should_fail=True))

    with tenant_context("beta"):
        with caplog.at_level(logging.INFO):
            run = await service.run(
                session,
                tenant_id=tenant.id,
                template=template,
                template_version=version,
                context={},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="job-2",
                output_basename="report",
            )

    warning_record = next(
        r for r in caplog.records if r.message == "PDF conversion failed; using fallback PDF"
    )
    assert warning_record.error_code == "pdf_conversion_timeout"
    assert warning_record.tenant == "beta"

    success_record = next(r for r in caplog.records if r.message == "Pipeline job finished")
    assert success_record.job_id == run.id
    assert success_record.pdf_fallback is True

    persisted = await session.get(PipelineRun, run.id)
    assert persisted is not None
    assert persisted.status is PipelineRunStatus.DONE
    assert persisted.result_metadata.get("pdf_fallback") is True
    assert persisted.result_metadata.get("pdf_error") == "pdf_conversion_timeout"


@pytest.mark.asyncio()
async def test_pipeline_idempotent_run_is_reused(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "gamma"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())

    with tenant_context("gamma"):
        run1 = await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={"name": "Alice"},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="reuse-me",
            output_basename="analysis",
        )
        run2 = await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={"name": "Alice"},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="reuse-me",
            output_basename="analysis",
        )

    assert run1 is run2
    assert run2.status is PipelineRunStatus.DONE
    assert run2.docx_storage_key is not None
    assert run2.pdf_storage_key is not None

    rows = (await session.execute(select(PipelineRun))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio()
async def test_pipeline_idempotency_conflict_different_payload(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "delta"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())

    with tenant_context("delta"):
        await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={"name": "Bob"},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="conflict-key",
            output_basename="report",
        )

        with pytest.raises(ValueError, match="Idempotency key collision"):
            await service.run(
                session,
                tenant_id=tenant.id,
                template=template,
                template_version=version,
                context={"name": "Charlie"},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="conflict-key",
                output_basename="report",
            )


@pytest.mark.asyncio()
async def test_pipeline_idempotency_conflict_different_template(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "zeta"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())

    with tenant_context("zeta"):
        await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={"name": "Eve"},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="template-conflict",
            output_basename="report",
        )

        other_template = Template(
            tenant_id=tenant.id, name="secondary", description=None, metadata_json={}
        )
        session.add(other_template)
        await session.flush()

        other_version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=other_template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key=version.payload_key,
        )
        session.add(other_version)
        await session.flush()

        with pytest.raises(ValueError, match="Idempotency key collision"):
            await service.run(
                session,
                tenant_id=tenant.id,
                template=other_template,
                template_version=other_version,
                context={"name": "Eve"},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="template-conflict",
                output_basename="report",
            )


@pytest.mark.asyncio()
async def test_pipeline_run_idempotency_key_unique_constraint(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "epsilon"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())

    with tenant_context("epsilon"):
        run = await service.run(
            session,
            tenant_id=tenant.id,
            template=template,
            template_version=version,
            context={},
            replacements=None,
            header_text=None,
            footer_text=None,
            idempotency_key="unique-key",
            output_basename="report",
        )

    duplicate = PipelineRun(
        tenant_id=tenant.id,
        template_id=run.template_id,
        template_version_id=run.template_version_id,
        status=PipelineRunStatus.QUEUED,
        context={},
        idempotency_key="unique-key",
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


@pytest.mark.asyncio()
async def test_pipeline_rejects_slug_passed_as_tenant_id(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())

    with tenant_context("acme"):
        with pytest.raises(ValueError, match="Template version belongs to a different tenant"):
            await service.run(
                session,
                tenant_id=tenant.slug,
                template=template,
                template_version=version,
                context={"name": "Jane"},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="slug-is-not-id",
                output_basename="report",
            )


@pytest.mark.asyncio()
async def test_pipeline_rejects_partial_session_tenant_contract(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())
    session.info["tenant_slug"] = tenant.slug
    session.info["tenant"] = tenant.slug

    with tenant_context("beta"):
        with pytest.raises(ValueError, match="tenant session contract is incomplete"):
            await service.run(
                session,
                tenant_id=tenant.id,
                template=template,
                template_version=version,
                context={"name": "Ivan"},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="partial-session-contract",
                output_basename="report",
            )


@pytest.mark.asyncio()
async def test_pipeline_rejects_session_tenant_mismatch(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_docx(monkeypatch)
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "gamma"))).scalar_one()
    other_tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == "delta"))
    ).scalar_one()
    template, version = await _prepare_template(session, tenant)
    service = PipelineService(pdf_converter=_FakePdfConverter())
    session.info["tenant_id"] = other_tenant.id
    session.info["tenant_slug"] = other_tenant.slug
    session.info["tenant"] = other_tenant.slug

    with tenant_context("gamma"):
        with pytest.raises(ValueError, match="Session tenant does not match template tenant"):
            await service.run(
                session,
                tenant_id=tenant.id,
                template=template,
                template_version=version,
                context={"name": "Mismatch"},
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key="mismatch-session-contract",
                output_basename="report",
            )


@pytest.mark.asyncio()
async def test_pipeline_run_json_columns_track_top_level_inplace_mutation(
    session: AsyncSession,
) -> None:
    """`PipelineRun.outputs`/`result_metadata` are MutableDict-wrapped, so a
    TOP-LEVEL in-place edit is persisted even WITHOUT reassigning a fresh object.

    Before the wrapper this lost the update (plain JSON column tracks only by
    object identity). Nested edits still require fresh reassignment.
    """
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
    template, version = await _prepare_template(session, tenant)
    run = PipelineRun(
        tenant_id=tenant.id,
        template_id=template.id,
        template_version_id=version.id,
        status=PipelineRunStatus.QUEUED,
        context={},
        outputs={"docx": "a"},
        result_metadata={"pdf_fallback": False},
        idempotency_key="mutable-tracking",
    )
    session.add(run)
    await session.commit()

    # In-place top-level mutation, NO reassignment of run.outputs / result_metadata.
    run.outputs["pdf"] = "b"
    run.result_metadata["pdf_fallback"] = True
    await session.commit()
    await session.refresh(run)

    assert run.outputs == {"docx": "a", "pdf": "b"}
    assert run.result_metadata == {"pdf_fallback": True}
