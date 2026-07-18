from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConvertPdfOptions(BaseModel):
    timeout_s: int = Field(default=45, ge=5, le=120)
    embed_fonts: bool = True


class ConvertPdfRequest(BaseModel):
    mode: str = Field(default="docx_to_pdf")
    options: ConvertPdfOptions = Field(default_factory=ConvertPdfOptions)


class ConvertPdfAccepted(BaseModel):
    job_id: str
    pdf_run_id: str
    output_file_id: str | None = None
    status_url: str


class PdfRunRead(BaseModel):
    id: str
    input_file_id: str
    output_file_id: str | None
    status: str
    timeout_s: int
    attempts: int
    error_code: str | None
    error_payload: dict
    correlation_id: str | None
    created_by: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
