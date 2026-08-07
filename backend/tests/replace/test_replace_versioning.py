from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pytest
from docx import Document

from app.models.document import DocumentVersion
from app.models.file import File
from app.modules.replace.service import create_document_version_from_bytes, execute_replace
from app.services.file_storage import FileStorageService


class _ExecResult:
    def __init__(self, value: int | None) -> None:
        self._value = value

    def scalar_one(self) -> int | None:
        return self._value


class FakeSession:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, obj: object) -> None:
        self.items.append(obj)

    def add_all(self, objs: list[object]) -> None:
        self.items.extend(objs)

    async def flush(self) -> None:
        for obj in self.items:
            if hasattr(obj, "id") and not getattr(obj, "id"):
                setattr(obj, "id", str(uuid4()))

    async def execute(self, _query):
        versions = [x for x in self.items if isinstance(x, DocumentVersion)]
        return _ExecResult(max((v.version_number for v in versions), default=None))


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.mark.asyncio
async def test_replace_apply_creates_new_document_version_and_increments_version_number() -> None:
    session = FakeSession()
    storage = FileStorageService.default()
    storage.clear()

    source_bytes = _docx_bytes("hello world")
    storage.put("source.docx", source_bytes)
    base = DocumentVersion(
        tenant_id="t1",
        document_id="d1",
        template_version="1",
        data_json={},
        file_key="source.docx",
        version_number=1,
        status="draft",
    )
    session.add(base)

    _, created = await create_document_version_from_bytes(
        session=session,
        tenant_id="t1",
        source_version=base,
        content=source_bytes,
        storage=storage,
        key_suffix="replace",
    )

    assert created.document_id == "d1"
    assert created.version_number == 2


@pytest.mark.asyncio
async def test_replace_apply_returns_document_version_id_not_file_key() -> None:
    session = FakeSession()
    storage = FileStorageService.default()
    storage.clear()
    source_bytes = _docx_bytes("alpha")

    base = DocumentVersion(
        tenant_id="t1",
        document_id="d2",
        template_version="1",
        data_json={},
        file_key="source_2.docx",
        version_number=1,
        status="draft",
    )
    session.add(base)

    file_row, created = await create_document_version_from_bytes(
        session=session,
        tenant_id="t1",
        source_version=base,
        content=source_bytes,
        storage=storage,
        key_suffix="replace",
    )

    assert created.id != file_row.storage_key
    assert created.file_key == file_row.storage_key


@pytest.mark.asyncio
async def test_replace_rollback_creates_new_version_from_target_version() -> None:
    session = FakeSession()
    storage = FileStorageService.default()
    storage.clear()

    v1_bytes = _docx_bytes("v1")
    storage.put("v1.docx", v1_bytes)
    v1 = DocumentVersion(
        tenant_id="t1",
        document_id="d3",
        template_version="1",
        data_json={},
        file_key="v1.docx",
        version_number=1,
        status="draft",
    )
    v2 = DocumentVersion(
        tenant_id="t1",
        document_id="d3",
        template_version="1",
        data_json={},
        file_key="v2.docx",
        version_number=2,
        status="draft",
    )
    session.add_all([v1, v2])

    _, restored = await create_document_version_from_bytes(
        session=session,
        tenant_id="t1",
        source_version=v1,
        content=storage.get(v1.file_key),
        storage=storage,
        key_suffix="rollback",
    )

    assert restored.version_number == 3
    assert storage.get(restored.file_key) == v1_bytes
    assert restored.file_key != v1.file_key


@pytest.mark.asyncio
async def test_replace_dry_run_produces_report_file() -> None:
    session = FakeSession()
    storage = FileStorageService.default()
    storage.clear()

    source_bytes = _docx_bytes("ООО Ромашка")
    storage.put("dry.docx", source_bytes)
    base = DocumentVersion(
        tenant_id="t1",
        document_id="d4",
        template_version="1",
        data_json={},
        file_key="dry.docx",
        version_number=1,
        status="draft",
    )
    session.add(base)

    result = await execute_replace(
        session=session,
        tenant_id="t1",
        source_version=base,
        rules=[{"from": "Ромашка", "to": "Лютик"}],
        case_sensitive=False,
        whole_word=False,
        storage=storage,
        run_id="run-1",
    )

    assert isinstance(result.report_file, File)
    assert storage.has(result.report_file_key)
    assert result.hits_count >= 1
