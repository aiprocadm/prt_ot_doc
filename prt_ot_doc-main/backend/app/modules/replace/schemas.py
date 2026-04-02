from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReplaceRule(BaseModel):
    from_: str = Field(alias="from")
    to: str
    flags: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class ReplaceMapCreate(BaseModel):
    code: str
    name: str
    source_type: str = "inline"
    rules: list[dict[str, Any]] = Field(default_factory=list)
    exclusions: dict[str, Any] = Field(default_factory=dict)


class ReplaceMapPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    rules: list[dict[str, Any]] | None = None
    exclusions: dict[str, Any] | None = None


class ReplaceMapRead(ReplaceMapCreate):
    id: str
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)


class ReplaceMapList(BaseModel):
    items: list[ReplaceMapRead]


class ReplaceOptions(BaseModel):
    case_sensitive: bool = False
    whole_word: bool = False
    regex_enabled: bool = False
    scope: list[str] = Field(default_factory=lambda: ["body", "tables", "hdr", "ftr", "shapes"])


class ReplaceLaunchRequest(BaseModel):
    replace_map_code: str | None = None
    replace_map_id: str | None = None
    options: ReplaceOptions = Field(default_factory=ReplaceOptions)




class ReplaceRollbackRequest(BaseModel):
    target_document_version_id: str | None = None
    rollback_to_version_number: int | None = None

class ReplaceLaunchResponse(BaseModel):
    job_id: str
    replace_run_id: str
    status_url: str | None = None
    new_document_version_id: str | None = None
    document_id: str | None = None
    version_number: int | None = None
    file_id: str | None = None
    file_key: str | None = None
    restored_from_version_id: str | None = None
    report_file_id: str | None = None
    report_file_key: str | None = None
    hits_count: int | None = None
    examples: list[dict[str, Any]] = Field(default_factory=list)


class ReplaceRunRead(BaseModel):
    id: str
    tenant_id: str
    document_version_id: str
    replace_map_id: str
    mode: str
    options: dict[str, Any]
    report_json: dict[str, Any]
    before_file_id: str
    after_file_id: str | None
    status: str

    model_config = ConfigDict(from_attributes=True)
