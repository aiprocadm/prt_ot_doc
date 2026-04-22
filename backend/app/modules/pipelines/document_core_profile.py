"""Canonical document-core pipeline profile (template → выпуск).

Единый порядок этапов для оркестратора заданий и для readiness/checklist в UI.
"""

from __future__ import annotations

from typing import Any


DOCUMENT_ORCHESTRATION_STATES: tuple[str, ...] = (
    "generated",
    "headers_applied",
    "pdf_ready",
    "handoff_ready",
    "failed",
    "retrying",
)

# Ключи шагов job engine (совпадают с step_key в DocumentJobStep после алиасов).
DOCUMENT_CORE_PIPELINE_STEPS: tuple[str, ...] = (
    "validate_template",
    "render_docx",
    "apply_headers",
    "replace",
    "quality_gate",
    "convert_pdf",
    "build_zip",
    "send_for_approval",
    "sign",
    "send_edo",
    "archive",
)

DOCUMENT_CORE_STEP_LABELS_RU: dict[str, str] = {
    "validate_template": "Проверка шаблона и версии",
    "render_docx": "Рендер DOCX из шаблона",
    "apply_headers": "Колонтитулы (hdr/ftr)",
    "replace": "Подстановка плейсхолдеров",
    "quality_gate": "Контроль качества перед выпуском",
    "convert_pdf": "Конвертация в PDF",
    "build_zip": "Сборка ZIP (при необходимости)",
    "send_for_approval": "Передача на согласование",
    "sign": "Подписание",
    "send_edo": "Отправка в ЭДО",
    "archive": "Архивирование",
}


def default_document_core_steps_json() -> list[dict[str, Any]]:
    """Список шагов для профиля без graph (steps_json)."""
    return [{"code": code} for code in DOCUMENT_CORE_PIPELINE_STEPS]


def default_document_core_graph(*, template_code: str) -> dict[str, Any]:
    """Эталонный граф для конструктора профилей (nodes/edges)."""
    nodes: list[dict[str, Any]] = [
        {"id": "validate", "type": "validate_template", "config": {}},
        {
            "id": "render",
            "type": "render_docx",
            "config": {"template_code": template_code},
        },
        {"id": "headers", "type": "apply_headers", "config": {}},
        {"id": "replace", "type": "replace_apply", "config": {}},
        {"id": "quality", "type": "quality_gate", "config": {}},
        {"id": "pdf", "type": "convert_pdf", "config": {}},
        {"id": "zip", "type": "build_zip", "config": {}},
        {"id": "approval", "type": "send_for_approval", "config": {}},
        {"id": "sign", "type": "verify_signature", "config": {}},
        {"id": "edo", "type": "send_edo", "config": {}},
        {"id": "archive", "type": "archive", "config": {}},
    ]
    edges = [
        {"from": "validate", "to": "render"},
        {"from": "render", "to": "headers"},
        {"from": "headers", "to": "replace"},
        {"from": "replace", "to": "quality"},
        {"from": "quality", "to": "pdf"},
        {"from": "pdf", "to": "zip"},
        {"from": "zip", "to": "approval"},
        {"from": "approval", "to": "sign"},
        {"from": "sign", "to": "edo"},
        {"from": "edo", "to": "archive"},
    ]
    return {"nodes": nodes, "edges": edges}
