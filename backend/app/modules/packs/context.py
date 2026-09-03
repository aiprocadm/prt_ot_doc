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
    PACK_CODE_BDD_REPORTS,
    PACK_CODE_CEO_SHIELD,
    PACK_CODE_CIVIL_DEFENCE,
    PACK_CODE_CONTRACTOR,
    PACK_CODE_ECO_REPORTS,
    PACK_CODE_FIRE_INSPECTION,
    PACK_CODE_GOCHS_REPORTS,
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_NEW_COMPANY,
    PACK_CODE_NEW_EMPLOYEE,
    PACK_CODE_OPO,
    PACK_CODE_OPO_REPORTS,
    PACK_CODE_ROAD_SAFETY,
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


def _ensure_person_alias(context: dict[str, Any]) -> None:
    """Собрать ``person.full_name`` из частей имени.

    Конвейер кладёт в контекст ``first_name``/``last_name``/``middle_name``, а
    шаблоны просят ``full_name`` — и получали ПУСТУЮ строку. В личной карточке
    учёта СИЗ это выглядит как графа «Работник:» без работника: документ
    напечатан, подписан и недействителен.
    """

    person = context.setdefault("person", {})
    if not isinstance(person, dict) or person.get("full_name"):
        return
    parts = [person.get("last_name"), person.get("first_name"), person.get("middle_name")]
    person["full_name"] = " ".join(str(part).strip() for part in parts if part) or "—"


def _ensure_named_block(context: dict[str, Any], key: str, fields: dict[str, Any]) -> None:
    """Завести блок контекста (``position``, ``journal``), не затирая данные.

    Блок мог прийти от конвейера — тогда заполняем только пустые поля.
    Прочерк вместо пустоты намеренный: пустая графа читается как брак печати,
    прочерк — как «не заполнено».
    """

    block = context.setdefault(key, {})
    if not isinstance(block, dict):
        return
    for field, value in fields.items():
        if not block.get(field):
            block[field] = value


def _apply_site_access(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    _ensure_person_alias(context)
    # Карточка СИЗ просит должность, лист журнала — название и тип журнала.
    # Ни того, ни другого конвейер в контекст не кладёт, и обе графы выходили
    # пустыми у ПЕРВОГО же сценария каталога.
    _ensure_named_block(context, "position", {"name": _coerce_text(data.get("position"))})
    _ensure_named_block(
        context,
        "journal",
        {
            "title": _coerce_text(data.get("journal_title"), "Журнал инструктажей"),
            "journal_type": _coerce_text(data.get("journal_type"), "Вводный инструктаж"),
        },
    )
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
    # Поля карточки СИЗ и листа журнала. Без умолчаний они выходили ПУСТЫМИ:
    # «Выданные СИЗ:» без перечня и «Дата:» без даты — это не документ, а бланк,
    # который уже подшили в папку как заполненный.
    payload.setdefault("issues", _format_list(data.get("issues")))
    payload.setdefault("norms", _format_list(data.get("norms")))
    payload.setdefault("ppe_officer", _coerce_text(data.get("ppe_officer"), ot_resp))
    payload.setdefault("entry_date", _coerce_text(data.get("entry_date")))
    payload.setdefault("instructor", _coerce_text(data.get("instructor"), ot_resp))
    payload.setdefault("person", _coerce_text(data.get("person")))
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


# --- Срез-3: контекст сценариев, добавленных срезом-2 -------------------------
#
# Пакет без строителя контекста получает только псевдоним ИНН: ни логотипа, ни
# печати, ни значений ``data.*``. Сгенерированный комплект выходит с пустыми
# графами — и это видно уже у клиента, а не на проверке. Ниже — по строителю на
# каждый сценарий; прочерк вместо пустоты означает «не заполнено», а не «сбой».


def _apply_new_employee(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    _ensure_person_alias(context)
    ot_resp = _coerce_text(data.get("ot_responsible"), "Ответственный не назначен")
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)
    context["ot_responsible"] = ot_resp
    context["hazards"] = _format_list(data.get("hazards"))

    payload = context.setdefault("data", {})
    person = context.get("person") if isinstance(context.get("person"), dict) else {}
    payload.setdefault(
        "employee_name", _coerce_text(data.get("employee_name") or person.get("full_name"))
    )
    payload.setdefault("position", _coerce_text(data.get("position")))
    payload.setdefault("hire_date", _coerce_text(data.get("hire_date")))
    payload.setdefault(
        "program", _coerce_text(data.get("program"), "Программа вводного инструктажа")
    )
    payload.setdefault("workplace", _coerce_text(data.get("workplace")))
    payload.setdefault("instructions", _format_list(data.get("instructions")))
    payload.setdefault("internship_days", _coerce_text(data.get("internship_days"), "не требуется"))
    payload.setdefault("medical_org", _coerce_text(data.get("medical_org")))
    payload.setdefault("ppe_norms", _format_list(data.get("ppe_norms")))
    payload.setdefault("sizes", _coerce_text(data.get("sizes")))
    payload.setdefault("documents", _format_list(data.get("documents")))
    # Подпись работника — графа для ручного заполнения, а не «неизвестно».
    payload.setdefault("employee_sign", _coerce_text(data.get("employee_sign"), "____________"))
    return context


def _apply_contractor(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    ot_resp = _coerce_text(data.get("ot_responsible"), "Ответственный не назначен")
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)
    context["ot_responsible"] = ot_resp
    context["work_types"] = _format_list(data.get("work_types"))
    context["hazards"] = _format_list(data.get("hazards"))

    payload = context.setdefault("data", {})
    payload.setdefault("contractor_name", _coerce_text(data.get("contractor_name")))
    payload.setdefault("contractor_inn", _coerce_text(data.get("contractor_inn")))
    payload.setdefault("contractor_responsible", _coerce_text(data.get("contractor_responsible")))
    payload.setdefault("headcount", _coerce_text(data.get("headcount")))
    payload.setdefault("permits", _format_list(data.get("permits")))
    # Статусы проверки готовности: умолчание «не подтверждено» — потому что
    # незаполненная проверка это НЕ пройденная проверка.
    for field in (
        "training_status",
        "medical_status",
        "ppe_status",
        "permits_status",
        "insurance_status",
    ):
        payload.setdefault(field, _coerce_text(data.get(field), "не подтверждено"))
    payload.setdefault("responsibility_split", _coerce_text(data.get("responsibility_split")))
    payload.setdefault("session_date", _coerce_text(data.get("session_date")))
    payload.setdefault("team_members", _format_list(data.get("team_members")))
    return context


def _apply_fire_inspection(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    pb_resp = _coerce_text(data.get("pb_responsible"), "Ответственный не назначен")
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)
    context["pb_responsible"] = pb_resp

    payload = context.setdefault("data", {})
    for field in ("extinguishers", "escape_routes", "alarm_systems", "fire_doors"):
        payload.setdefault(field, _coerce_text(data.get(field), "не проверено"))
    payload.setdefault("findings", _format_list(data.get("findings"), "замечаний нет"))
    payload.setdefault("fire_works_rules", _coerce_text(data.get("fire_works_rules")))
    payload.setdefault("shutdown_rules", _coerce_text(data.get("shutdown_rules")))
    payload.setdefault("housekeeping", _coerce_text(data.get("housekeeping")))
    payload.setdefault("fire_actions", _coerce_text(data.get("fire_actions")))
    payload.setdefault("evacuation", _coerce_text(data.get("evacuation")))
    payload.setdefault("drill_date", _coerce_text(data.get("drill_date")))
    payload.setdefault("drill_result", _coerce_text(data.get("drill_result"), "не проводилась"))
    payload.setdefault("scenario", _coerce_text(data.get("scenario")))
    payload.setdefault("team_members", _format_list(data.get("team_members")))
    payload.setdefault("system_name", _coerce_text(data.get("system_name")))
    payload.setdefault("system_result", _coerce_text(data.get("system_result"), "не проверено"))
    payload.setdefault("next_check_date", _coerce_text(data.get("next_check_date")))
    return context


def _apply_civil_defence(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    payload = context.setdefault("data", {})
    payload.setdefault(
        "gochs_responsible",
        _coerce_text(data.get("gochs_responsible"), "Ответственный не назначен"),
    )
    payload.setdefault("threats", _format_list(data.get("threats")))
    payload.setdefault("notification_order", _coerce_text(data.get("notification_order")))
    payload.setdefault("resources", _format_list(data.get("resources")))
    payload.setdefault(
        "facility_category", _coerce_text(data.get("facility_category"), "не отнесён")
    )
    payload.setdefault("protection_storage", _coerce_text(data.get("protection_storage")))
    payload.setdefault("commission_head", _coerce_text(data.get("commission_head")))
    payload.setdefault("commission_members", _format_list(data.get("commission_members")))
    payload.setdefault("commission_tasks", _format_list(data.get("commission_tasks")))
    payload.setdefault("scenario", _coerce_text(data.get("scenario")))
    payload.setdefault("drill_date", _coerce_text(data.get("drill_date")))
    payload.setdefault("team_members", _format_list(data.get("team_members")))
    payload.setdefault("lesson_topic", _coerce_text(data.get("lesson_topic")))
    payload.setdefault("session_date", _coerce_text(data.get("session_date")))
    return context


def _apply_road_safety(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """БДД (BIZ-54-57 срез-5): подстановки базового комплекта.

    Умолчания намеренно ГОВОРЯЩИЕ, а не пустые: документ с прочерком на месте
    ответственного за БДД выглядит оформленным, хотя ответственного нет.
    """

    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    payload = context.setdefault("data", {})
    payload.setdefault(
        "bdd_responsible",
        _coerce_text(data.get("bdd_responsible"), "Ответственный не назначен"),
    )
    payload.setdefault(
        "bdd_attestation_date", _coerce_text(data.get("bdd_attestation_date"), "не проходил")
    )
    payload.setdefault("bdd_fleet_scope", _coerce_text(data.get("bdd_fleet_scope")))
    payload.setdefault("bdd_dispatch_order", _coerce_text(data.get("bdd_dispatch_order")))
    payload.setdefault("bdd_medical_check_order", _coerce_text(data.get("bdd_medical_check_order")))
    payload.setdefault("bdd_tech_check_order", _coerce_text(data.get("bdd_tech_check_order")))
    payload.setdefault("bdd_driver_schedule", _coerce_text(data.get("bdd_driver_schedule")))
    payload.setdefault("bdd_plan_period", _coerce_text(data.get("bdd_plan_period")))
    payload.setdefault("bdd_measures", _format_list(data.get("bdd_measures")))
    payload.setdefault("bdd_completion_note", _coerce_text(data.get("bdd_completion_note")))
    payload.setdefault("bdd_director", _coerce_text(data.get("bdd_director")))
    payload.setdefault("bdd_briefing_kind", _coerce_text(data.get("bdd_briefing_kind")))
    payload.setdefault("bdd_briefing_topics", _format_list(data.get("bdd_briefing_topics")))
    payload.setdefault("bdd_briefing_hours", _coerce_text(data.get("bdd_briefing_hours")))
    payload.setdefault("bdd_briefing_date", _coerce_text(data.get("bdd_briefing_date")))
    return context


def _apply_gochs_reports(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Отчётность ГО и ЧС (разд. 56.1 срез-6): подстановки комплекта.

    Умолчания ЧЕСТНЫЕ, и в донесении о ЧС это критично: незаполненное число
    пострадавших читается «сведения не внесены», а НЕ «ноль». Подставь ноль —
    и донесение В ОРГАН УПРАВЛЕНИЯ заявит, что пострадавших нет, хотя их
    просто не успели посчитать. Донесение подают в первые часы, когда как раз
    и не знают точных чисел.
    """

    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    payload = context.setdefault("data", {})
    payload.setdefault(
        "gochs_report_author", _coerce_text(data.get("gochs_report_author"), "не указан")
    )
    payload.setdefault(
        "gochs_responsible",
        _coerce_text(data.get("gochs_responsible"), "Ответственный не назначен"),
    )
    payload.setdefault(
        "gochs_approved_by", _coerce_text(data.get("gochs_approved_by"), "не утверждено")
    )
    payload.setdefault(
        "facility_category",
        _coerce_text(data.get("facility_category"), "не установлена"),
    )
    # числовые ответы: пусто = «сведения не внесены», а НЕ ноль
    for number_field in (
        "gochs_event_injured",
        "gochs_formations_count",
        "gochs_personnel_count",
        "gochs_ppe_coverage",
    ):
        payload.setdefault(
            number_field, _coerce_text(data.get(number_field), "сведения не внесены")
        )
    for text_field in (
        "gochs_unit_modes",
        "gochs_alert_order",
        "gochs_evacuation_order",
        "gochs_shelters",
        "gochs_event_at",
        "gochs_event_kind",
        "gochs_report_period",
        "gochs_alert_means",
    ):
        payload.setdefault(text_field, _coerce_text(data.get(text_field)))
    for list_field in (
        "gochs_unit_structure",
        "gochs_unit_tasks",
        "gochs_staff_actions",
        "gochs_event_measures",
        "gochs_event_forces",
    ):
        payload.setdefault(list_field, _format_list(data.get(list_field)))
    return context


def _apply_bdd_reports(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Отчётность БДД (разд. 56.2 срез-9): подстановки комплекта.

    Умолчания ЧЕСТНЫЕ, и это здесь важнее обычного: незаполненное число ДТП
    читается «сведения не внесены», а НЕ «ноль». Подставь ноль — и отчёт о
    состоянии аварийности заявит, что происшествий не было, хотя их просто
    не внесли. Молчание нельзя выдавать за благополучие (довод превышений ПЭК
    в отчётных формах экологии).
    """

    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    payload = context.setdefault("data", {})
    payload.setdefault(
        "bdd_report_period", _coerce_text(data.get("bdd_report_period"), "не указан")
    )
    payload.setdefault(
        "bdd_report_author", _coerce_text(data.get("bdd_report_author"), "не указан")
    )
    payload.setdefault(
        "bdd_responsible",
        _coerce_text(data.get("bdd_responsible"), "Ответственный не назначен"),
    )
    payload.setdefault(
        "bdd_approved_by", _coerce_text(data.get("bdd_approved_by"), "не утверждено")
    )
    # числовые ответы: пусто = «сведения не внесены», а НЕ ноль
    for number_field in (
        "bdd_report_vehicles",
        "bdd_report_drivers",
        "bdd_report_accidents",
        "bdd_report_injured",
        "bdd_report_violations",
        "bdd_measures_planned",
        "bdd_measures_done",
    ):
        payload.setdefault(
            number_field, _coerce_text(data.get(number_field), "сведения не внесены")
        )
    payload.setdefault("bdd_goals", _format_list(data.get("bdd_goals")))
    payload.setdefault("bdd_control_order", _coerce_text(data.get("bdd_control_order")))
    payload.setdefault("bdd_review_order", _coerce_text(data.get("bdd_review_order")))
    payload.setdefault(
        "bdd_measures_failed_reason",
        _coerce_text(data.get("bdd_measures_failed_reason")),
    )
    payload.setdefault(
        "bdd_assignment_date", _coerce_text(data.get("bdd_assignment_date"))
    )
    payload.setdefault(
        "bdd_assignment_list", _format_list(data.get("bdd_assignment_list"))
    )
    return context


def _apply_eco_reports(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Отчётные формы экологии (разд. 55.3): подстановки комплекта.

    Умолчания говорящие и ЧЕСТНЫЕ: пустой ответ про превышения читается
    «сведения не внесены», а не «превышений не было» — молчание нельзя
    выдавать за благополучие. Суммы платы без ответа — «не внесено», а не
    ноль: «ноль рублей» и «не внесено» — разные утверждения (довод «норматив
    не внесён» из замеров ПЭК).
    """

    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    payload = context.setdefault("data", {})
    payload.setdefault("eco_report_year", _coerce_text(data.get("eco_report_year"), "не указан"))
    payload.setdefault("eco_responsible", _coerce_text(data.get("eco_responsible"), "не указан"))
    for money_field in (
        "eco_fee_emissions",
        "eco_fee_discharges",
        "eco_fee_waste",
        "eco_fee_advances",
    ):
        payload.setdefault(money_field, _coerce_text(data.get(money_field), "не внесено"))
    payload.setdefault(
        "eco_pek_exceedances",
        _coerce_text(data.get("eco_pek_exceedances"), "сведения не внесены"),
    )
    for plain_field in (
        "eco_waste_generated",
        "eco_waste_transferred",
        "eco_waste_disposed",
        "eco_air_emitted",
        "eco_air_sources",
        "eco_air_treatment",
        "eco_water_intake",
        "eco_water_discharge",
        "eco_water_meters",
        "eco_pek_program",
        "eco_pek_measurements",
        "eco_pek_laboratory",
        "eco_nvos_number",
        "eco_nvos_category",
        "eco_nvos_actualization",
    ):
        payload.setdefault(plain_field, _coerce_text(data.get(plain_field)))
    return context


def _apply_opo_reports(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Отчётность ПромБез (разд. 54.2 срез-42): подстановки комплекта.

    Умолчания ЧЕСТНЫЕ, и в сведениях для Ростехнадзора это критично:
    незаполненное число аварий, просроченных ЭПБ или аттестаций читается
    «сведения не внесены», а НЕ «ноль». Подставь ноль — и отчёт В НАДЗОРНЫЙ
    ОРГАН заявит, что инцидентов не было и просрочек нет, хотя их просто не
    посчитали. Отвечает за это подписавший.
    """

    _ensure_company_alias(context)
    context["logo"] = _decode_image(data.get("logo"), DEFAULT_LOGO_BYTES)
    context["stamp"] = _decode_image(data.get("stamp"), DEFAULT_STAMP_BYTES)

    payload = context.setdefault("data", {})
    payload.setdefault(
        "opo_report_author", _coerce_text(data.get("opo_report_author"), "не указан")
    )
    payload.setdefault("opo_report_year", _coerce_text(data.get("opo_report_year"), "не указан"))
    payload.setdefault(
        "opo_pc_responsible",
        _coerce_text(data.get("opo_pc_responsible"), "Ответственный не назначен"),
    )
    payload.setdefault(
        "opo_approved_by", _coerce_text(data.get("opo_approved_by"), "не утверждено")
    )
    payload.setdefault("opo_director", _coerce_text(data.get("opo_director"), "не указан"))
    # числовые ответы: пусто = «сведения не внесены», а НЕ ноль
    for number_field in (
        "opo_facilities_count",
        "opo_devices_count",
        "opo_epb_done",
        "opo_epb_overdue",
        "opo_attestations_count",
        "opo_attestations_overdue",
        "opo_pc_measures_planned",
        "opo_pc_measures_done",
        "opo_incidents_count",
    ):
        payload.setdefault(
            number_field, _coerce_text(data.get(number_field), "сведения не внесены")
        )
    # «нарушений не выявлено» — утверждение, которое платформа за специалиста
    # не делает: молчание нельзя выдавать за благополучие
    payload.setdefault(
        "opo_violations_note",
        _coerce_text(data.get("opo_violations_note"), "сведения не внесены"),
    )
    for text_field in (
        "opo_pc_attestation",
        "opo_pc_inspection_order",
        "opo_pc_reporting_order",
        "opo_order_date",
        "opo_facilities_by_class",
        "opo_incident_period",
        "opo_incident_downtime",
    ):
        payload.setdefault(text_field, _coerce_text(data.get(text_field)))
    for list_field in (
        "opo_pc_tasks",
        "opo_facility_responsibles",
        "opo_incident_causes",
        "opo_incident_measures",
    ):
        payload.setdefault(list_field, _format_list(data.get(list_field)))
    return context


_BUILDERS: dict[str, Builder] = {
    PACK_CODE_SITE_ACCESS: _apply_site_access,
    PACK_CODE_NEW_COMPANY: _apply_new_company,
    PACK_CODE_INCIDENT: _apply_incident,
    PACK_CODE_INSPECTION_PREP: _apply_inspection,
    PACK_CODE_OPO: _apply_opo,
    PACK_CODE_WASTE: _apply_waste,
    PACK_CODE_CEO_SHIELD: _apply_ceo_shield,
    PACK_CODE_NEW_EMPLOYEE: _apply_new_employee,
    PACK_CODE_CONTRACTOR: _apply_contractor,
    PACK_CODE_FIRE_INSPECTION: _apply_fire_inspection,
    PACK_CODE_CIVIL_DEFENCE: _apply_civil_defence,
    PACK_CODE_ROAD_SAFETY: _apply_road_safety,
    PACK_CODE_BDD_REPORTS: _apply_bdd_reports,
    PACK_CODE_GOCHS_REPORTS: _apply_gochs_reports,
    PACK_CODE_ECO_REPORTS: _apply_eco_reports,
    PACK_CODE_OPO_REPORTS: _apply_opo_reports,
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
