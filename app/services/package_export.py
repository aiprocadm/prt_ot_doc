from __future__ import annotations

import logging
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Callable, Iterable, Sequence

from app.core.config import get_settings
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.domains.files.utils import build_dated_prefix
from app.domains.files import s3
from app.services.file_storage import FileStorageService

logger = logging.getLogger(__name__)

__all__ = [
    "ExportDocument",
    "ExportedDocument",
    "PackageExportResult",
    "PackageExportService",
]


_CYRILLIC_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_VALID_SEGMENT = re.compile(r"^[a-z0-9_]+$")
_MAX_STORAGE_KEY = 120


@dataclass(slots=True)
class ExportDocument:
    """Descriptor for a generated document that should be placed into a ZIP archive."""

    template_id: str
    template_name: str
    version: int
    person_id: str | None
    person_label: str | None
    document_version_id: str | None
    docx_storage_key: str | None
    pdf_storage_key: str | None


@dataclass(slots=True)
class ExportedDocument:
    """Information about a document stored inside the generated ZIP archive."""

    template_id: str
    template_name: str
    person_id: str | None
    basename: str
    document_version_id: str | None
    docx_storage_key: str | None
    pdf_storage_key: str | None
    docx_zip_path: str | None
    pdf_zip_path: str | None


@dataclass(slots=True)
class PackageExportResult:
    """Result metadata for a generated package archive."""

    zip_storage_key: str
    documents: list[ExportedDocument]


class PackageExportService:
    """Assemble generated documents into a tenant-scoped ZIP archive."""

    ZIP_CONTENT_TYPE = "application/zip"

    def __init__(
        self,
        *,
        storage: FileStorageService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._storage = storage or FileStorageService.default()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def export(
        self,
        *,
        tenant_slug: str,
        pack_code: str,
        org: str,
        unit: str,
        project: str,
        client: str,
        topic: str,
        version: int,
        reference_date: date,
        flags: Sequence[str] = (),
        documents: Iterable[ExportDocument],
    ) -> PackageExportResult:
        """Bundle ``documents`` into a ZIP archive stored in the tenant bucket."""

        sanitized_flags = tuple(self._slugify(flag, default="") for flag in flags if flag)
        pack_slug = self._slugify(pack_code, default="package")
        org_slug = self._slugify(org)
        unit_slug = self._slugify(unit)
        project_slug = self._slugify(project)
        client_slug = self._slugify(client)
        topic_slug = self._slugify(topic)

        archive_buffer = io.BytesIO()
        exported: list[ExportedDocument] = []

        with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for descriptor in documents:
                doc_slug = self._slugify(descriptor.template_name)
                basename = self._compose_basename(
                    org=org_slug,
                    unit=unit_slug,
                    project=project_slug,
                    client=client_slug,
                    doc=doc_slug,
                    topic=topic_slug,
                    version=version,
                    reference_date=reference_date,
                    flags=sanitized_flags,
                )
                person_segment = self._slugify(descriptor.person_label or "brigade")
                folder = f"{pack_slug}/{person_segment}"

                docx_path: str | None = None
                pdf_path: str | None = None

                if descriptor.docx_storage_key:
                    data = self._storage.get(descriptor.docx_storage_key)
                    docx_path = f"{folder}/{basename}.docx"
                    zf.writestr(docx_path, data)
                if descriptor.pdf_storage_key:
                    data = self._storage.get(descriptor.pdf_storage_key)
                    pdf_path = f"{folder}/{basename}.pdf"
                    zf.writestr(pdf_path, data)

                exported.append(
                    ExportedDocument(
                        template_id=descriptor.template_id,
                        template_name=descriptor.template_name,
                        person_id=descriptor.person_id,
                        basename=basename,
                        document_version_id=descriptor.document_version_id,
                        docx_storage_key=descriptor.docx_storage_key,
                        pdf_storage_key=descriptor.pdf_storage_key,
                        docx_zip_path=docx_path,
                        pdf_zip_path=pdf_path,
                    )
                )

        archive_bytes = archive_buffer.getvalue()
        timestamp = self._now().strftime("%Y%m%d%H%M%S")
        archive_name = self._compose_basename(
            org=org_slug,
            unit=unit_slug,
            project=project_slug,
            client=client_slug,
            doc=pack_slug,
            topic=topic_slug,
            version=max(1, version),
            reference_date=reference_date,
            flags=sanitized_flags,
        )
        now = datetime.now(tz=timezone.utc)
        prefix = build_dated_prefix(tenant_slug, now=now)
        raw_key = f"{prefix}/packages/{pack_slug}/{timestamp}-{archive_name}.zip"
        storage_key = self._truncate_storage_key(raw_key)
        metrics = get_metrics()
        upload_start = perf_counter()
        metrics.record_pipeline_stage_start(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.STORED_S3,
        )
        try:
            self._storage.put(
                storage_key, archive_bytes, content_type=self.ZIP_CONTENT_TYPE
            )
        except Exception as exc:
            metrics.record_pipeline_stage_end(
                pipeline=PipelineType.DOCUMENT,
                stage=PipelineStage.STORED_S3,
                result=StageResult.FAILED,
                seconds=perf_counter() - upload_start,
                error_class=exc.__class__.__name__,
            )
            raise
        metrics.record_pipeline_stage_end(
            pipeline=PipelineType.DOCUMENT,
            stage=PipelineStage.STORED_S3,
            result=StageResult.SUCCESS,
            seconds=perf_counter() - upload_start,
        )
        settings = get_settings()
        if settings.s3_backend == "minio":
            try:
                s3.put_object(data=archive_bytes, mime=self.ZIP_CONTENT_TYPE, key=storage_key)
            except Exception as exc:  # pragma: no cover - network guard
                logger.warning(
                    "package_export.s3_upload_failed",
                    extra={"bucket": settings.s3_bucket, "key": storage_key},
                    exc_info=exc,
                )
        return PackageExportResult(zip_storage_key=storage_key, documents=exported)

    def _slugify(self, value: str | None, *, default: str = "na") -> str:
        if not value:
            return default
        normalized = unicodedata.normalize("NFKD", value)
        buffer: list[str] = []
        for character in normalized.lower():
            if character in _CYRILLIC_TRANSLIT:
                buffer.append(_CYRILLIC_TRANSLIT[character])
                continue
            if character.isascii() and character.isalnum():
                buffer.append(character)
                continue
            if character in {" ", "-", ".", "/"}:
                buffer.append("_")
        slug = re.sub(r"_+", "_", "".join(buffer)).strip("_")
        if not slug:
            return default
        if not _VALID_SEGMENT.match(slug):
            slug = re.sub(r"[^a-z0-9_]", "", slug)
        return slug or default

    def _compose_basename(
        self,
        *,
        org: str,
        unit: str,
        project: str,
        client: str,
        doc: str,
        topic: str,
        version: int,
        reference_date: date,
        flags: Sequence[str],
    ) -> str:
        version_token = f"v{version:02d}"
        date_token = reference_date.strftime("%Y%m%d")
        parts = [org, unit, project, client, doc, topic, version_token, date_token]
        filtered = [part for part in parts if part]
        base = "_".join(filtered)
        if flags:
            base = f"{base}_{'_'.join(flags)}"
        return base

    def _truncate_storage_key(self, key: str) -> str:
        if len(key) <= _MAX_STORAGE_KEY:
            return key
        prefix, _, suffix = key.rpartition("/")
        if not prefix:
            return key[-_MAX_STORAGE_KEY:]
        name, dot, ext = suffix.partition(".")
        extension = f"{dot}{ext}" if dot else ""
        max_name_length = _MAX_STORAGE_KEY - len(prefix) - 1 - len(extension)
        if max_name_length <= 0:
            truncated = extension or suffix[:1]
            return f"{prefix}/{truncated}"
        truncated_name = name[:max_name_length] or "archive"
        return f"{prefix}/{truncated_name}{extension}"
