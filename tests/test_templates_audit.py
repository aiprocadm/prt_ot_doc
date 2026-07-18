"""Tests for the template migration / quality audit service
(Phase 5.1 / vNext-DOC-02, Session 37).

Uses a dict-backed loader so tests do not depend on the real file storage
backend. Persistence is intentionally not tested — the audit service is
read-only.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

import pytest
from sqlalchemy import select

from app.models.models import (
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.modules.templates import audit_template_versions


def _docx(text: str) -> bytes:
    bio = BytesIO()
    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return bio.getvalue()


class _DictLoader:
    """Tiny in-memory file-storage stub used by tests."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.fail_keys: set[str] = set()

    def add(self, key: str, payload: bytes) -> None:
        self.store[key] = payload

    def __call__(self, key: str) -> bytes:
        if key in self.fail_keys:
            raise RuntimeError(f"forced failure for {key}")
        return self.store.get(key, b"")


async def _seed_template(
    session,
    *,
    tenant_id: str,
    code: str,
    name: str = "Test template",
    versions: list[dict[str, Any]] | None = None,
    template_deleted: bool = False,
) -> Template:
    template = Template(
        tenant_id=tenant_id,
        code=code,
        name=name,
        description="",
        metadata_json={},
        storage_key=f"templates/{code}.docx",
    )
    session.add(template)
    await session.flush()
    if template_deleted:
        from datetime import datetime, timezone

        template.deleted_at = datetime.now(timezone.utc)
    for spec in versions or []:
        version = TemplateVersion(
            tenant_id=tenant_id,
            template_id=template.id,
            version=spec.get("version", 1),
            checksum=spec.get("checksum", b"chk"),
            status=spec.get("status", TemplateVersionStatus.ACTIVE),
            payload_key=spec.get("payload_key", f"templates/{code}.docx"),
            file_id=spec.get("file_id"),
            required_fields_schema=spec.get("required_fields_schema"),
        )
        session.add(version)
        await session.flush()
        if spec.get("deleted"):
            from datetime import datetime, timezone

            version.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return template


@pytest.mark.anyio
async def test_audit_empty_db_returns_empty_report(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=_DictLoader(),
        )
    assert report.total == 0
    assert report.total_errors == 0
    assert report.total_warnings == 0
    assert report.total_ok == 0
    assert report.to_dict()["summary"] == {"total": 0, "ok": 0, "warnings": 0, "errors": 0}


@pytest.mark.anyio
async def test_audit_clean_template_marked_ok(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/clean.docx", _docx("{{ employee.name }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="clean",
            versions=[{"payload_key": "templates/clean.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total == 1
    assert report.total_ok == 1
    assert report.items[0].severity == "ok"
    assert report.items[0].errors == []


@pytest.mark.anyio
async def test_audit_broken_template_marked_error(sessionmaker) -> None:
    loader = _DictLoader()
    # Unclosed {% if %} -> linter raises "Unclosed blocks" error
    loader.add("templates/broken.docx", _docx("{% if user.active %}{{ user.name }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="broken",
            versions=[{"payload_key": "templates/broken.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total == 1
    assert report.total_errors == 1
    item = report.items[0]
    assert item.severity == "error"
    assert any("Unclosed blocks" in err for err in item.errors)


@pytest.mark.anyio
async def test_audit_warning_only_template_marked_warning(sessionmaker) -> None:
    loader = _DictLoader()
    # Unknown filter -> linter warns but no errors
    loader.add("templates/warn.docx", _docx("{{ name | madeupfilter }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="warn",
            versions=[{"payload_key": "templates/warn.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total_warnings == 1
    assert report.items[0].severity == "warning"
    assert any("Unknown filter" in w and "madeupfilter" in w for w in report.items[0].warnings)


@pytest.mark.anyio
async def test_audit_uses_required_fields_schema_for_undefined_check(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/schema.docx", _docx("{{ employee.name }} {{ contractor.legal_name }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="with-schema",
            versions=[
                {
                    "payload_key": "templates/schema.docx",
                    "required_fields_schema": {"employee": {"name": ""}},
                }
            ],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    item = report.items[0]
    assert any("contractor.legal_name" in w for w in item.warnings), item.warnings


@pytest.mark.anyio
async def test_audit_skips_soft_deleted_template_version(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/ghost.docx", _docx("{{ a }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="ghost",
            versions=[{"payload_key": "templates/ghost.docx", "deleted": True}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total == 0


@pytest.mark.anyio
async def test_audit_skips_soft_deleted_template(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/ghost-template.docx", _docx("{{ a }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="ghost-template",
            versions=[{"payload_key": "templates/ghost-template.docx"}],
            template_deleted=True,
        )
        await session.commit()
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total == 0


@pytest.mark.anyio
async def test_audit_load_failure_recorded_as_load_error(sessionmaker) -> None:
    loader = _DictLoader()
    loader.fail_keys.add("templates/missing.docx")
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="missing",
            versions=[{"payload_key": "templates/missing.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total_errors == 1
    item = report.items[0]
    assert item.severity == "error"
    assert item.load_error is not None
    assert item.load_error.startswith("FILE_LOAD_FAILED")


@pytest.mark.anyio
async def test_audit_empty_payload_recorded_as_load_error(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/empty.docx", b"")
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="empty",
            versions=[{"payload_key": "templates/empty.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    item = report.items[0]
    assert item.severity == "error"
    assert item.load_error == "EMPTY_PAYLOAD"


@pytest.mark.anyio
async def test_audit_template_id_filter_narrows_scan(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/a.docx", _docx("{{ a }}"))
    loader.add("templates/b.docx", _docx("{{ b }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        t_a = await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="a",
            versions=[{"payload_key": "templates/a.docx"}],
        )
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="b",
            versions=[{"payload_key": "templates/b.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
            template_id=t_a.id,
        )
    assert report.total == 1
    assert report.items[0].template_code == "a"


@pytest.mark.anyio
async def test_audit_multiple_versions_per_template_all_listed(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/multi-v1.docx", _docx("{{ a }}"))
    loader.add("templates/multi-v2.docx", _docx("{{ b }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="multi",
            versions=[
                {"version": 1, "payload_key": "templates/multi-v1.docx"},
                {"version": 2, "payload_key": "templates/multi-v2.docx"},
            ],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    assert report.total == 2
    versions = sorted(item.version_number for item in report.items)
    assert versions == [1, 2]


def test_validate_templates_cli_text_format_renders_summary() -> None:
    """Smoke test for the CLI text-format helper.

    Imports from ``scripts/audit/validate_templates.py`` directly. Kept here
    rather than in a separate file because the CLI is a thin wrapper around
    ``audit_template_versions`` and the test belongs with audit coverage.
    """
    import importlib.util
    from pathlib import Path

    cli_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "audit" / "validate_templates.py"
    )
    spec = importlib.util.spec_from_file_location("validate_templates_cli", cli_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    report = {
        "summary": {"total": 3, "ok": 1, "warnings": 1, "errors": 1},
        "items": [
            {
                "template_id": "t1",
                "template_code": "clean",
                "template_name": "Clean",
                "tenant_id": "test",
                "version_id": "v1",
                "version_number": 1,
                "status": "active",
                "file_key": "templates/clean.docx",
                "errors": [],
                "warnings": [],
                "summary": {"field_count": 1},
                "load_error": None,
                "severity": "ok",
            },
            {
                "template_id": "t2",
                "template_code": "warn",
                "template_name": "Warn",
                "tenant_id": "test",
                "version_id": "v2",
                "version_number": 1,
                "status": "active",
                "file_key": "templates/warn.docx",
                "errors": [],
                "warnings": ["Unknown filter '|nope'"],
                "summary": {"field_count": 1, "warning_count": 1},
                "load_error": None,
                "severity": "warning",
            },
            {
                "template_id": "t3",
                "template_code": "broken",
                "template_name": "Broken",
                "tenant_id": "test",
                "version_id": "v3",
                "version_number": 1,
                "status": "linted",
                "file_key": "templates/broken.docx",
                "errors": ["Unclosed blocks: if"],
                "warnings": [],
                "summary": {"field_count": 1, "error_count": 1},
                "load_error": None,
                "severity": "error",
            },
        ],
    }
    text = module._format_text(report)
    assert "Total versions scanned : 3" in text
    assert "OK                   : 1" in text
    assert "Warnings only        : 1" in text
    assert "Errors / load fails  : 1" in text
    assert "-- ERROR" in text
    assert "-- WARNING" in text
    assert "-- OK" in text
    assert "Unclosed blocks: if" in text


def test_validate_templates_cli_text_format_handles_empty_report() -> None:
    import importlib.util
    from pathlib import Path

    cli_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "audit" / "validate_templates.py"
    )
    spec = importlib.util.spec_from_file_location("validate_templates_cli", cli_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = module._format_text(
        {"summary": {"total": 0, "ok": 0, "warnings": 0, "errors": 0}, "items": []}
    )
    assert "No template versions to audit." in text


@pytest.mark.anyio
async def test_audit_report_to_dict_shape(sessionmaker) -> None:
    loader = _DictLoader()
    loader.add("templates/shape.docx", _docx("{{ employee.name }}"))
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_template(
            session,
            tenant_id=tenant.slug,
            code="shape",
            versions=[{"payload_key": "templates/shape.docx"}],
        )
        report = await audit_template_versions(
            session,
            tenant_id=tenant.slug,
            loader=loader,
        )
    payload = report.to_dict()
    assert set(payload) == {"summary", "items"}
    assert set(payload["summary"]) == {"total", "ok", "warnings", "errors"}
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert {
        "template_id",
        "template_code",
        "version_id",
        "version_number",
        "errors",
        "warnings",
        "summary",
        "severity",
    } <= set(item)
