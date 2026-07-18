from __future__ import annotations

import tempfile
from typing import Any

from app.modules.doc_render.passport import embed_passport_docx


def inject_passport(docx_bytes: bytes, passport: dict[str, Any], *, visible: bool = False) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".docx") as tmp:
        tmp.write(docx_bytes)
        tmp.flush()
        embed_passport_docx(tmp.name, passport, visible=visible)
        tmp.seek(0)
        return tmp.read()
