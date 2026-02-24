from __future__ import annotations


def embed_pdf_passport(pdf_bytes: bytes, passport: dict[str, object] | None) -> bytes:
    if not passport:
        return pdf_bytes
    marker = ("\n% PTD-PASSPORT " + str(passport).replace("\n", " ")).encode("utf-8")
    return pdf_bytes + marker
