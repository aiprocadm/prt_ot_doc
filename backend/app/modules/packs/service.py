from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import compute_request_hash
from app.models.file import File
from app.models.models import (
    PackLogLevel,
    PackRun,
    PackRunItem,
    PackRunItemStatus,
    PackRunLifecycleStatus,
    PackageEntityStatus,
    PackagePresetConfig,
    PackagePresetItem,
    PackageProfileConfig,
    PackageSourceType,
    TemplateUsage,
    TemplateVersion,
    TemplateVersionStatus,
)
from app.modules.packs.schemas import PackRunCreate, PackagePresetItemCreate


class NamingRuleEngine:
    TOKEN_RE = re.compile(r"<([a-zA-Z_]+)>")
    BAD_CHARS_RE = re.compile(r"[\\/:*?\"<>|]+")

    def render(self, rule: str, payload: dict[str, Any], ext: str = "docx") -> str:
        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(payload.get(key, "")).strip()

        value = self.TOKEN_RE.sub(_replace, rule)
        value = self.BAD_CHARS_RE.sub("_", value)
        value = re.sub(r"\s+", " ", value).strip(" ._")
        value = value[:180] if len(value) > 180 else value
        return f"{value or 'document'}.{ext}"


class SourceImportService:
    def parse(self, source_type: str, content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
        if source_type == "json":
            rows = json.loads(content.decode("utf-8"))
            if not isinstance(rows, list):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON source must be an array")
            normalized = [self._normalize_row(dict(row)) for row in rows]
            columns = sorted({k for row in normalized for k in row.keys()})
            return columns, normalized
        if source_type == "csv":
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = [self._normalize_row(dict(row)) for row in reader]
            return [self._norm_col(c) for c in (reader.fieldnames or [])], rows
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source type is not supported in this build")

    def _norm_col(self, column: str | None) -> str:
        return (column or "").strip().lower()

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            normalized[self._norm_col(key)] = value
        return normalized


class MappingValidationService:
    def validate(self, mapping: dict[str, Any], columns: list[str]) -> None:
        known = set(columns)
        for target, source in mapping.items():
            if isinstance(source, str) and source.strip().lower() not in known:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"missing source column for mapping {target}")
            if isinstance(source, dict):
                if source.get("type") == "column" and str(source.get("value", "")).strip().lower() not in known:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"missing source column for mapping {target}")
                if source.get("type") not in {"column", "literal"}:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid computed mapping type")

    def apply(self, mapping: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for target, source in mapping.items():
            if isinstance(source, str):
                result[target] = row.get(source.strip().lower())
            elif isinstance(source, dict) and source.get("type") == "literal":
                result[target] = source.get("value")
            elif isinstance(source, dict) and source.get("type") == "column":
                result[target] = row.get(str(source.get("value", "")).strip().lower())
        return result


class PackageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_profile(self, tenant_id: str, payload: dict[str, Any]) -> PackageProfileConfig:
        profile = PackageProfileConfig(tenant_id=tenant_id, **payload)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def list_profiles(self, tenant_id: str) -> list[PackageProfileConfig]:
        stmt: Select[tuple[PackageProfileConfig]] = select(PackageProfileConfig).where(
            PackageProfileConfig.tenant_id == tenant_id,
            PackageProfileConfig.deleted_at.is_(None),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_profile(self, tenant_id: str, profile_id: str) -> PackageProfileConfig | None:
        stmt = select(PackageProfileConfig).where(
            PackageProfileConfig.tenant_id == tenant_id,
            PackageProfileConfig.id == profile_id,
            PackageProfileConfig.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_preset(self, tenant_id: str, payload: dict[str, Any]) -> PackagePresetConfig:
        preset = PackagePresetConfig(tenant_id=tenant_id, **payload)
        self.session.add(preset)
        await self.session.flush()
        return preset

    async def get_preset(self, tenant_id: str, preset_id: str) -> PackagePresetConfig | None:
        stmt = select(PackagePresetConfig).where(
            PackagePresetConfig.tenant_id == tenant_id,
            PackagePresetConfig.id == preset_id,
            PackagePresetConfig.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_presets(self, tenant_id: str) -> list[PackagePresetConfig]:
        stmt = select(PackagePresetConfig).where(
            PackagePresetConfig.tenant_id == tenant_id,
            PackagePresetConfig.deleted_at.is_(None),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_item(self, tenant_id: str, preset: PackagePresetConfig, payload: PackagePresetItemCreate) -> PackagePresetItem:
        tv = await self.session.get(TemplateVersion, payload.template_version_id)
        if tv is None or tv.tenant_id != tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "template version not found")
        if tv.deleted_at is not None or tv.status in {TemplateVersionStatus.ARCHIVED, TemplateVersionStatus.DEPRECATED}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "template version is invalid for package")
        item = PackagePresetItem(
            tenant_id=tenant_id,
            package_preset_id=preset.id,
            template_id=payload.template_id or tv.template_id,
            template_version_id=payload.template_version_id,
            order_no=payload.order_no,
            header_preset_json=payload.header_preset_json,
            replace_mode=payload.replace_mode,
            replace_map_json=payload.replace_map_json,
            output_format=payload.output_format,
            is_required=payload.is_required,
            conditions_json=payload.conditions_json,
        )
        self.session.add(item)
        self.session.add(
            TemplateUsage(
                tenant_id=tenant_id,
                template_version_id=payload.template_version_id,
                used_by_type="package_preset",
                used_by_id=preset.id,
            )
        )
        await self.session.flush()
        return item


class PackRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.naming = NamingRuleEngine()
        self.mapping = MappingValidationService()

    async def create_run(
        self,
        *,
        tenant_id: str,
        payload: PackRunCreate,
        idempotency_key: str,
        rows: list[dict[str, Any]],
    ) -> PackRun:
        preset = await self.session.get(PackagePresetConfig, payload.package_preset_id)
        if preset is None or preset.tenant_id != tenant_id or preset.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "package preset not found")
        if preset.status != PackageEntityStatus.ACTIVE and preset.status != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "package preset must be active")

        selected_rows = payload.selected_rows or list(range(1, len(rows) + 1))
        req_hash = compute_request_hash(
            {
                "package_preset_id": payload.package_preset_id,
                "selected_rows": selected_rows,
                "override_profile_id": payload.override_profile_id,
                "override_options": payload.override_options,
                "rows": rows,
            }
        )
        existing = (
            await self.session.execute(
                select(PackRun).where(
                    PackRun.tenant_id == tenant_id,
                    PackRun.idempotency_key == idempotency_key,
                    PackRun.request_hash == req_hash,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        self.mapping.validate(preset.mapping_json or {}, list(rows[0].keys()) if rows else [])
        run = PackRun(
            tenant_id=tenant_id,
            package_preset_id=preset.id,
            package_profile_id=payload.override_profile_id or preset.package_profile_id,
            source_file_id=payload.source_file_id,
            source_type=preset.source_type,
            source_rows_count=len(rows),
            selected_rows_count=len(selected_rows),
            status=PackRunLifecycleStatus.SUCCESS,
            stats_json={"queued": len(selected_rows), "success": len(selected_rows), "failed": 0},
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            request_hash=req_hash,
        )
        self.session.add(run)
        await self.session.flush()
        for row_no in selected_rows:
            if row_no < 1 or row_no > len(rows):
                continue
            mapped = self.mapping.apply(preset.mapping_json or {}, rows[row_no - 1])
            filename = self.naming.render(preset.naming_rule, mapped, ext="docx")
            self.session.add(
                PackRunItem(
                    tenant_id=tenant_id,
                    pack_run_id=run.id,
                    row_no=row_no,
                    source_record_hash=hashlib.sha1(json.dumps(rows[row_no - 1], sort_keys=True).encode("utf-8")).hexdigest(),
                    status=PackRunItemStatus.SUCCESS,
                    filename=filename,
                )
            )
        return run


async def ensure_template_version_deletable(session: AsyncSession, tenant_id: str, template_version_id: str) -> None:
    usage = (
        await session.execute(
            select(TemplateUsage).where(
                TemplateUsage.tenant_id == tenant_id,
                TemplateUsage.template_version_id == template_version_id,
                TemplateUsage.used_by_type == "package_preset",
            )
        )
    ).scalar_one_or_none()
    if usage:
        raise HTTPException(status.HTTP_409_CONFLICT, "template version is used by package preset")


async def load_source_rows(session: AsyncSession, source_file_id: str | None, inline_rows: list[dict[str, Any]]) -> tuple[str, list[str], list[dict[str, Any]]]:
    if inline_rows:
        cols = sorted({k.strip().lower() for row in inline_rows for k in row.keys()})
        normalized = [{k.strip().lower(): v for k, v in row.items()} for row in inline_rows]
        return "json", cols, normalized
    if not source_file_id:
        return "json", [], []
    file = await session.get(File, source_file_id)
    if file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source file not found")
    raw = (file.meta_json or {}).get("inline_content")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source file has no inline content for preview")
    content = raw.encode("utf-8")
    source_type = (file.meta_json or {}).get("source_type", "csv")
    columns, rows = SourceImportService().parse(source_type=source_type, content=content)
    return source_type, columns, rows
