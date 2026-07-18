from __future__ import annotations

import os
import tempfile
from typing import Any

from app.modules.doc_render.passport import embed_passport_docx


def inject_passport(docx_bytes: bytes, passport: dict[str, Any], *, visible: bool = False) -> bytes:
    """Write docx to a temp path, embed passport, read back.

    On Windows a :class:`~tempfile.NamedTemporaryFile` keeps the handle open and
    blocks a second ``open()`` on the same path; use mkstemp + close before read.
    """

    fd, path = tempfile.mkstemp(suffix=".docx")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(docx_bytes)
        embed_passport_docx(path, passport, visible=visible)
        with open(path, "rb") as inp:
            return inp.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
