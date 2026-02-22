from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

STEP_CODES = {
    "render_docx",
    "apply_headers",
    "replace",
    "convert_pdf",
    "build_zip",
    "archive",
    "send_edo",
    "index_content",
}

KNOWN_SCHEMAS = {
    "RenderParamsV1",
    "HeadersParamsV1",
    "ReplaceParamsV1",
    "PdfParamsV1",
    "ZipParamsV1",
    "ArchiveParamsV1",
    "EdoParamsV1",
}


class PipelineStepSchema(BaseModel):
    code: str
    required: bool = True
    params_schema: str

    @model_validator(mode="after")
    def validate_known_values(self) -> "PipelineStepSchema":
        if self.code not in STEP_CODES:
            raise ValueError(f"unsupported step code: {self.code}")
        if self.params_schema not in KNOWN_SCHEMAS:
            raise ValueError(f"unsupported params schema: {self.params_schema}")
        return self


class PipelineLimitsSchema(BaseModel):
    max_parallel: int = Field(default=1, ge=1, le=64)
    max_parallel_per_step: dict[str, int] = Field(default_factory=dict)


class PipelineProfileCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    steps: list[PipelineStepSchema]
    limits: PipelineLimitsSchema = Field(default_factory=PipelineLimitsSchema)
    is_active: bool = True

    model_config = ConfigDict(extra="forbid")


class PipelineProfilePatch(BaseModel):
    name: str | None = None
    steps: list[PipelineStepSchema] | None = None
    limits: PipelineLimitsSchema | None = None
    is_active: bool | None = None


class PipelineProfileRead(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    steps: list[PipelineStepSchema]
    limits: PipelineLimitsSchema
    version: int


class PipelineRunRequest(BaseModel):
    profile_code: str
    input: dict[str, Any]
    overrides: dict[str, Any] | None = None


class PipelineRunAccepted(BaseModel):
    job_id: str
    status_url: str
    ws_channel: str


class JobActionRequest(BaseModel):
    step_code: str | None = None
    restart_from_order: int | None = None


JobStatusLiteral = Literal["queued", "running", "success", "failed", "canceled"]
