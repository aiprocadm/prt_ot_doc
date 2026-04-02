from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PackageProfileCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    pipeline_steps_json: list[dict[str, Any]] = Field(default_factory=list)
    concurrency_limit: int | None = None
    status: str = "draft"


class PackageProfilePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    pipeline_steps_json: list[dict[str, Any]] | None = None
    concurrency_limit: int | None = None
    status: str | None = None


class PackageProfileRead(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    pipeline_steps_json: list[dict[str, Any]]
    concurrency_limit: int | None
    status: str


class PackagePresetCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    package_profile_id: str
    naming_rule: str
    source_type: str
    mapping_json: dict[str, Any] = Field(default_factory=dict)
    options_json: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"


class PackagePresetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    package_profile_id: str | None = None
    naming_rule: str | None = None
    source_type: str | None = None
    mapping_json: dict[str, Any] | None = None
    options_json: dict[str, Any] | None = None
    status: str | None = None


class PackagePresetItemCreate(BaseModel):
    order_no: int
    template_id: str | None = None
    template_version_id: str
    header_preset_json: dict[str, Any] | None = None
    replace_mode: str = "none"
    replace_map_json: dict[str, Any] | None = None
    output_format: str = "both"
    is_required: bool = True
    conditions_json: dict[str, Any] | None = None


class PackagePresetItemPatch(BaseModel):
    order_no: int | None = None
    template_id: str | None = None
    template_version_id: str | None = None
    header_preset_json: dict[str, Any] | None = None
    replace_mode: str | None = None
    replace_map_json: dict[str, Any] | None = None
    output_format: str | None = None
    is_required: bool | None = None
    conditions_json: dict[str, Any] | None = None


class PackagePresetItemRead(BaseModel):
    id: str
    order_no: int
    template_id: str | None
    template_version_id: str
    replace_mode: str
    output_format: str
    is_required: bool


class PackagePresetRead(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    package_profile_id: str
    naming_rule: str
    source_type: str
    mapping_json: dict[str, Any]
    options_json: dict[str, Any]
    status: str
    items: list[PackagePresetItemRead] = Field(default_factory=list)


class SourcePreviewRead(BaseModel):
    source_file_id: str | None = None
    source_type: str
    columns: list[str]
    rows_count: int
    sample_rows: list[dict[str, Any]]


class MappingPreviewRequest(BaseModel):
    source_file_id: str | None = None
    row_limit: int = 5
    rows: list[dict[str, Any]] = Field(default_factory=list)


class PackRunCreate(BaseModel):
    package_preset_id: str
    source_file_id: str | None = None
    selected_rows: list[int] = Field(default_factory=list)
    override_profile_id: str | None = None
    override_options: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class PackRunAccepted(BaseModel):
    pack_run_id: str
    status: str


class PackRunItemRead(BaseModel):
    id: str
    row_no: int
    status: str
    file_name: str
    error_code: str | None


class PackRunRead(BaseModel):
    id: str
    package_preset_id: str
    package_profile_id: str
    status: str
    source_rows_count: int
    selected_rows_count: int
    stats_json: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class PackRunLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    level: str
    step: str | None
    message: str
    payload: dict[str, Any] | None
    created_at: datetime


class DownloadRead(BaseModel):
    url: str
