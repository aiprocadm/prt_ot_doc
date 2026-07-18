"""PipelineService preparation helpers (ARCH-4 slice 9 split)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.payload_constraints import (
    enforce_mapping_constraints,
    normalize_output_basename,
)
from app.models.models import PipelineRun, Template, TemplateVersion


class PreparationMixin:
    """Request-metadata build, parameter preparation and idempotent-run validation."""

    @staticmethod
    def _build_request_metadata(
        *,
        replacements: dict[str, str],
        header_text: str | None,
        footer_text: str | None,
        output_basename: str | None,
    ) -> dict[str, Any]:
        return {
            "replacements": replacements,
            "header_text": header_text,
            "footer_text": footer_text,
            "output_basename": output_basename,
        }

    def _prepare_parameters(
        self,
        *,
        session: AsyncSession,
        template: Template,
        template_version: TemplateVersion,
        context: dict[str, Any],
        replacements: dict[str, str] | None,
        header_text: str | None,
        footer_text: str | None,
        output_basename: str | None,
        tenant_id: str | None,
    ) -> tuple[str, str | None, dict[str, str], dict[str, Any]]:
        enforce_mapping_constraints(context, field="context")
        if replacements is not None:
            enforce_mapping_constraints(replacements, field="replacements")

        normalized_output_basename = normalize_output_basename(output_basename)

        tenant_identifier = str(tenant_id or template.tenant_id or "").strip()
        if not tenant_identifier:
            raise ValueError("Template is not bound to a tenant")
        if template_version.tenant_id and template_version.tenant_id != tenant_identifier:
            raise ValueError("Template version belongs to a different tenant")
        session_info = getattr(session, "info", None)
        session_tenant_id = None
        session_tenant_slug = None
        if isinstance(session_info, dict):
            session_tenant_id = str(session_info.get("tenant_id") or "").strip() or None
            session_tenant_slug = (
                str(session_info.get("tenant_slug") or session_info.get("tenant") or "").strip()
                or None
            )
        if session_tenant_slug and session_tenant_id is None:
            raise ValueError("Session tenant_id is missing; tenant session contract is incomplete")
        if session_tenant_id and session_tenant_id != tenant_identifier:
            raise ValueError("Session tenant does not match template tenant")

        replacements_map = dict(replacements or {})
        metadata = self._build_request_metadata(
            replacements=dict(replacements_map),
            header_text=header_text,
            footer_text=footer_text,
            output_basename=normalized_output_basename,
        )
        return tenant_identifier, normalized_output_basename, replacements_map, metadata

    @staticmethod
    def _validate_idempotent_run(
        run: PipelineRun,
        *,
        template_id: str,
        template_version_id: str,
        payload: dict[str, Any],
    ) -> None:
        if run.template_id != template_id or run.template_version_id != template_version_id:
            raise ValueError("Idempotency key collision for different template")
        if run.context != payload:
            raise ValueError("Idempotency key collision for different payload")
