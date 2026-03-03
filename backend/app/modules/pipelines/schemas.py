from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.pipelines.graph import PipelineGraph, PipelineProfileValidator

STEP_CODES = {"render_docx", "apply_headers", "replace", "convert_pdf", "build_zip", "archive", "send_edo", "index_content"}
KNOWN_SCHEMAS = {"RenderParamsV1", "HeadersParamsV1", "ReplaceParamsV1", "PdfParamsV1", "ZipParamsV1", "ArchiveParamsV1", "EdoParamsV1"}

JobStatusLiteral = Literal["queued", "running", "success", "failed", "canceled"]


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
    description: str | None = None
    steps: list[PipelineStepSchema] | None = None
    graph: PipelineGraph | None = None
    limits: PipelineLimitsSchema = Field(default_factory=PipelineLimitsSchema)
    is_active: bool = True
    concurrency_limit_per_tenant: int | None = Field(default=None, ge=1, le=256)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_graph_or_steps(self) -> "PipelineProfileCreate":
        if not self.steps and not self.graph:
            raise ValueError("steps or graph is required")
        if self.graph:
            PipelineProfileValidator().validate(self.graph)
        return self


class PipelineProfilePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[PipelineStepSchema] | None = None
    graph: PipelineGraph | None = None
    limits: PipelineLimitsSchema | None = None
    is_active: bool | None = None
    concurrency_limit_per_tenant: int | None = Field(default=None, ge=1, le=256)

    @model_validator(mode="after")
    def validate_graph(self) -> "PipelineProfilePatch":
        if self.graph:
            PipelineProfileValidator().validate(self.graph)
        return self


class PipelineProfileRead(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    is_active: bool
    steps: list[PipelineStepSchema] = Field(default_factory=list)
    graph: PipelineGraph | None = None
    limits: PipelineLimitsSchema
    profile_version: int = 1
    version: int
    concurrency_limit_per_tenant: int | None = None


class PipelineRunRequest(BaseModel):
    profile_code: str | None = None
    profile_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_profile_selector(self) -> "PipelineRunRequest":
        if not self.profile_code and not self.profile_id:
            raise ValueError("profile_code or profile_id is required")
        return self


class PipelineRunAccepted(BaseModel):
    run_id: str
    status: JobStatusLiteral
    step_runs: list[dict[str, Any]]


class PipelineStepRunRead(BaseModel):
    step_run_id: str
    run_id: str
    step_code: str
    status: str
    attempt: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None


class PipelineRunRead(BaseModel):
    run_id: str
    profile_id: str | None = None
    status: JobStatusLiteral
    inputs_json: dict[str, Any] | None = None
    outputs_json: dict[str, Any] | None = None
    created_by: str | None = None
    correlation_id: str | None = None
    step_runs: list[PipelineStepRunRead]


class JobActionRequest(BaseModel):
    step_code: str | None = None
    restart_from_order: int | None = None
