"""Pydantic-схемы report-builder API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportColumnMeta(BaseModel):
    key: str
    label: str
    kind: str
    aggregatable: bool = False
    enum_values: list[str] | None = None
    ops: list[str]


class ReportDatasetRead(BaseModel):
    code: str
    title: str
    columns: list[ReportColumnMeta]


class ReportDatasetPage(BaseModel):
    items: list[ReportDatasetRead]
    total: int


class ReportDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    dataset_code: str
    config_json: dict[str, Any] = Field(default_factory=dict)


class ReportDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    dataset_code: str | None = None
    config_json: dict[str, Any] | None = None


class ReportDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    dataset_code: str
    config_json: dict[str, Any]
    is_system: bool
    created_at: datetime
    updated_at: datetime


class ReportDefinitionPage(BaseModel):
    items: list[ReportDefinitionRead]
    total: int


class ReportPreviewIn(BaseModel):
    dataset_code: str
    config_json: dict[str, Any] = Field(default_factory=dict)


class ReportPreviewOut(BaseModel):
    columns: list[dict[str, str]]  # {key,label,kind}
    rows: list[dict[str, Any]]
    total: int


class ReportRunIn(BaseModel):
    format: Literal["csv", "xlsx", "pdf"]


class ReportRunOut(BaseModel):
    job_id: str
    status: str
