from __future__ import annotations

import hashlib
import io
import tempfile
from pathlib import Path

from app.core.utils.pdf_passport import embed_pdf_passport
from app.models.file import File, FileKind, FileScanStatus
from app.modules.files import s3
from app.modules.pdf.service_pool import LibreOfficePool
from app.modules.pdf.validators import PdfFontsValidationError, ensure_embedded_fonts


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def convert_docx_bytes(
    *,
    source_bytes: bytes,
    timeout_s: int,
    pool: LibreOfficePool,
    passport: dict[str, object] | None = None,
) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory(prefix="pdf-convert-") as td:
        workdir = Path(td)
        source = workdir / "source.docx"
        source.write_bytes(source_bytes)
        pdf_path = pool.convert(source=source, output_dir=workdir, timeout_s=timeout_s)
        ensure_embedded_fonts(pdf_path)
        payload = embed_pdf_passport(pdf_path.read_bytes(), passport)
        return payload, _sha256(payload)


def load_source_bytes(file: File) -> bytes:
    with s3.stream_object(key=file.storage_key) as stream:
        if isinstance(stream, io.BytesIO):
            return stream.getvalue()
        return stream.read()


def persist_pdf(
    *, tenant_prefix: str, source: File, pdf_bytes: bytes, sha256_hex: str
) -> tuple[str, str]:
    key = f"{tenant_prefix}/pdf/{source.id}-{sha256_hex[:12]}.pdf"
    s3.put_object(key=key, data=pdf_bytes, mime="application/pdf")
    return key, sha256_hex


def build_pdf_file(*, tenant_id: str, key: str, sha256_hex: str, size: int) -> File:
    return File(
        tenant_id=tenant_id,
        storage_key=key,
        bucket="generated",
        sha256=sha256_hex,
        size=size,
        mime="application/pdf",
        original_name="converted.pdf",
        meta_json={"generated_by": "convert_pdf_job"},
        kind=FileKind.DOCUMENT,
        is_quarantined=False,
        scan_status=FileScanStatus.CLEAN,
    )


def map_failure(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "PDF_TIMEOUT"
    if isinstance(exc, PdfFontsValidationError):
        return exc.code
    return "PDF_CONVERSION_FAILED"
