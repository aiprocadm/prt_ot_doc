"""Shared upload-size guard for multipart (``UploadFile``) endpoints.

Centralizes the ``413 Request Entity Too Large`` check every multipart
endpoint should apply *before* reading a body into memory. Starlette
populates ``UploadFile.size`` while parsing the multipart body, so the
value reflects the bytes actually received — a cheap, reliable pre-read
guard.

This is the lightweight path. For uploads that also need streaming
ingest with content-type sniffing and hashing, see
``routes/files.py::_ingest_upload``, which enforces the same
``settings.max_upload_size`` ceiling chunk-by-chunk.

``code`` / ``error_type`` are passed by the caller so each router keeps
its own problem-detail taxonomy (e.g. ``SOUT_IMPORT_TOO_LARGE`` / ``sout``,
``DOCUMENT_BATCH_FILE_TOO_LARGE`` / ``documents``).
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.errors import api_problem_detail

DEFAULT_OVERSIZE_MESSAGE = "Файл превышает максимальный размер загрузки"


def reject_oversize_upload(
    file: UploadFile,
    *,
    code: str,
    error_type: str,
    message: str = DEFAULT_OVERSIZE_MESSAGE,
    max_bytes: int | None = None,
) -> None:
    """Raise ``413`` when ``file`` exceeds the upload ceiling.

    ``max_bytes`` defaults to ``settings.max_upload_size``. The guard is
    strictly greater-than, so a file exactly at the limit is accepted.
    """
    limit = max_bytes if max_bytes is not None else get_settings().max_upload_size
    if (getattr(file, "size", None) or 0) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=api_problem_detail(code=code, message=message, error_type=error_type),
        )
