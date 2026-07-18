"""Helpers for enriching pack rendering context with domain specifics."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Callable

from app.modules.packs.assets import (
    DEFAULT_LOGO_BYTES,
    DEFAULT_STAMP_BYTES,
    build_inline_image_descriptor,
)
from app.modules.packs.definitions import (
    PACK_CODE_CEO_SHIELD,
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_NEW_COMPANY,
    PACK_CODE_OPO,
    PACK_CODE_SITE_ACCESS,
    PACK_CODE_WASTE,
)

__all__ = ["enrich_context"]


Builder = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _coerce_text(value: Any, default: str = "—") -> str:
    if value is None:
        return default
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(items) or default
    candidate = str(value).strip()
    return candidate or default


def _format_list(value: Any, default: str = "—") -> str:
    if value is None:
        return default
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        if not items:
            return default
        return "\n".join(f"- {item}" for item in items)
    candidate = str(value).strip()
    return candidate or default


def _decode_image(value: Any, fallback: bytes) -> dict[str, object]:
    if isinstance(value, dict):
        if value.get("_type") == "inline_image":
            return value
        data = value.get("data")
        width = value.get("width_mm")
        height = value.get("height_mm")
        if isinstance(data, str):
            try:
                payload = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error):
                payload = fallback
        elif isinstance(data, (bytes, bytearray)):
            payload = bytes(data)
        else:
            payload = fallback
        return build_inline_image_descriptor(
            payload, width_mm=width if width is not None else 45.0, height_mm=height
        )
    if isinstance(value, (bytes, bytearray)):
        return build_inline_image_descriptor(bytes(value))
    if isinstance(value, str):
        try:
            payload = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            payload = fallback
        return build_inline_image_descriptor(payload)
    return build_inline_image_descriptor(fallback)


def _ensure_company_alias(context: dict[str, Any]) -> None:
    company = context.get("company")
    if isinstance(company, dict):
        tax_id = company.get("tax_id")
        if "inn" not in company:
            company["inn"] = tax_id


def _apply_site_access(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    ot_resp = _coerce_text(data.get("ot_responsible"), "Ответственный не назначен")
    pb_resp = _coerce_text(data.get("pb_responsible"), "Ответственный не назначен")
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)
    context["ot_responsible"] = ot_resp
    context["pb_responsible"] = pb_resp
    context["work_types"] = _format_list(data.get("work_types"))
    context["hazards"] = _format_list(data.get("hazards"))

    payload = context.setdefault("data", {})
    payload.setdefault("session_date", _coerce_text(data.get("session_date")))
    payload.setdefault("team_members", _format_list(data.get("team_members")))
    payload.setdefault("training_passed", _coerce_text(data.get("training_passed"), "да"))
    payload.setdefault("medical_clearance", _coerce_text(data.get("medical_clearance"), "да"))
    payload.setdefault("ppe_ready", _coerce_text(data.get("ppe_ready"), "да"))
    payload.setdefault("notes", _coerce_text(data.get("notes")))
    payload.setdefault("supervisor", _coerce_text(data.get("supervisor")))
    payload["ot_responsible"] = ot_resp
    payload["pb_responsible"] = pb_resp
    payload["work_types"] = context["work_types"]
    payload["hazards"] = context["hazards"]
    return context


def _apply_new_company(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)
    payload = context.setdefault("data", {})
    payload.setdefault("issued_at", _coerce_text(data.get("issued_at")))
    payload.setdefault("ot_lead", _coerce_text(data.get("ot_lead")))
    payload.setdefault("pb_lead", _coerce_text(data.get("pb_lead")))
    payload.setdefault("policy_intro", _coerce_text(data.get("policy_intro")))
    payload.setdefault("employer_duties", _coerce_text(data.get("employer_duties")))
    payload.setdefault("employee_duties", _coerce_text(data.get("employee_duties")))
    payload.setdefault("journal_start", _coerce_text(data.get("journal_start")))
    payload.setdefault("journal_end", _coerce_text(data.get("journal_end")))
    payload.setdefault("journal_notes", _coerce_text(data.get("journal_notes")))
    return context


def _apply_incident(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    incident = {
        "date": _coerce_text(data.get("incident_date")),
        "location": _coerce_text(data.get("incident_location")),
        "description": _coerce_text(data.get("incident_description")),
        "deadline": _coerce_text(data.get("incident_deadline")),
    }
    context["incident"] = incident

    victim_payload = data.get("victim") if isinstance(data.get("victim"), dict) else {}
    context["victim"] = {
        "name": _coerce_text(victim_payload.get("name")),
        "position": _coerce_text(victim_payload.get("position")),
    }

    context["witnesses"] = _format_list(data.get("witnesses"))
    context["commission"] = _format_list(data.get("commission"))
    context["causes"] = _format_list(data.get("causes"))
    context["actions"] = _format_list(data.get("actions"))

    payload = context.setdefault("data", {})
    payload.setdefault("follow_up", _coerce_text(data.get("follow_up")))
    payload.setdefault("logo", context["logo"])
    payload.setdefault("stamp", context["stamp"])
    return context


def _apply_inspection(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    inspection = {
        "agency": _coerce_text(data.get("inspection_agency")),
        "date": _coerce_text(data.get("inspection_date")),
        "lead": _coerce_text(data.get("inspection_lead")),
        "scope": _coerce_text(data.get("inspection_scope")),
        "documents": _format_list(data.get("inspection_documents")),
        "risks": _format_list(data.get("inspection_risks")),
        "contacts": _format_list(data.get("inspection_contacts")),
    }
    context["inspection"] = inspection

    payload = context.setdefault("data", {})
    payload.setdefault("briefing_date", _coerce_text(data.get("briefing_date")))
    payload.setdefault("team", _format_list(data.get("team")))
    payload.setdefault("roles", _format_list(data.get("roles")))
    payload.setdefault("actions", _format_list(data.get("actions")))
    return context


def _apply_opo(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)
    context["hazards"] = _format_list(data.get("hazards"))

    opo = {
        "category": _coerce_text(data.get("opo_category")),
        "process": _coerce_text(data.get("opo_process")),
        "responsibles": _format_list(data.get("opo_responsibles")),
        "contacts": _format_list(data.get("opo_contacts")),
        "incidents": _format_list(data.get("opo_incidents")),
        "resources": _format_list(data.get("opo_resources")),
        "alerts": _format_list(data.get("opo_alerts")),
        "personnel": _format_list(data.get("opo_personnel")),
        "courses": _format_list(data.get("opo_courses")),
        "permits": _format_list(data.get("opo_permits")),
    }
    context["opo"] = opo
    return context


def _apply_waste(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    waste = {
        "types": _format_list(data.get("waste_types")),
        "classes": _format_list(data.get("waste_classes")),
        "storage": _format_list(data.get("waste_storage")),
        "removal": _format_list(data.get("waste_removal")),
        "contractor": _coerce_text(data.get("waste_contractor")),
        "contract_number": _coerce_text(data.get("waste_contract_number")),
        "contract_validity": _coerce_text(data.get("waste_contract_validity")),
        "responsibles": _format_list(data.get("waste_responsibles")),
        "instructions": _format_list(data.get("waste_instructions")),
        "control": _format_list(data.get("waste_control")),
    }
    context["waste"] = waste

    payload = context.setdefault("data", {})
    payload.setdefault("personnel", _format_list(data.get("personnel")))
    return context


def _apply_ceo_shield(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    shield = {
        "ot_lead": _coerce_text(data.get("ot_lead")),
        "pb_lead": _coerce_text(data.get("pb_lead")),
        "eco_lead": _coerce_text(data.get("eco_lead")),
        "ceo": _coerce_text(data.get("ceo")),
        "deputy": _coerce_text(data.get("deputy")),
        "scope": _coerce_text(data.get("delegation_scope")),
        "valid_until": _coerce_text(data.get("delegation_valid_until")),
        "risks": _format_list(data.get("director_risks")),
        "reporting": _format_list(data.get("reporting")),
        "contacts": _format_list(data.get("contacts")),
    }
    context["shield"] = shield
    return context


_BUILDERS: dict[str, Builder] = {
    PACK_CODE_SITE_ACCESS: _apply_site_access,
    PACK_CODE_NEW_COMPANY: _apply_new_company,
    PACK_CODE_INCIDENT: _apply_incident,
    PACK_CODE_INSPECTION_PREP: _apply_inspection,
    PACK_CODE_OPO: _apply_opo,
    PACK_CODE_WASTE: _apply_waste,
    PACK_CODE_CEO_SHIELD: _apply_ceo_shield,
}


def enrich_context(
    pack_code: str,
    context: dict[str, Any],
    payload_data: dict[str, Any],
) -> dict[str, Any]:
    """Return a context enriched with pack-specific placeholders."""

    builder = _BUILDERS.get(pack_code)
    if builder is None:
        _ensure_company_alias(context)
        return context
    return builder(context, payload_data)
