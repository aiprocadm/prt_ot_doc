from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from app.models.models import DocumentPack

SCENARIO_ALIASES: dict[str, str] = {
    "OUT_TO_SITE": "Выход на объект",
    "OT_ENTER_SITE": "Выход на объект",
    "INCIDENT": "Несчастный случай",
    "INCIDENT_RESPONSE": "Несчастный случай",
    "INSPECTION_PREP": "Подготовка к проверке",
    "OT_INSPECTION_PREP": "Подготовка к проверке",
}

DEFAULT_STEP_PROFILES: dict[str, list[dict[str, str]]] = {
    "Выход на объект": [
        {"code": "collect_requirements", "title": "Сбор данных клиента"},
        {"code": "validate_access", "title": "Проверка допусков и документов"},
        {"code": "generate_documents", "title": "Генерация комплекта"},
        {"code": "publish_portal", "title": "Публикация в клиентском кабинете"},
    ],
    "Несчастный случай": [
        {"code": "collect_requirements", "title": "Сбор обстоятельств и материалов"},
        {"code": "generate_documents", "title": "Формирование актов и приложений"},
        {"code": "quality_check", "title": "Проверка полноты расследования"},
        {"code": "publish_portal", "title": "Публикация в клиентском кабинете"},
    ],
    "Подготовка к проверке": [
        {"code": "collect_requirements", "title": "Сбор документов и вводных"},
        {"code": "gap_analysis", "title": "Gap analysis по требованиям"},
        {"code": "generate_documents", "title": "Формирование пакета к проверке"},
        {"code": "publish_portal", "title": "Публикация в клиентском кабинете"},
    ],
}


def resolve_scenario_label(code: str | None, fallback: str) -> str:
    normalized = str(code or "").strip().upper()
    return SCENARIO_ALIASES.get(normalized, fallback)


def resolve_pipeline_profile(
    *,
    preset_code: str | None,
    preset_name: str,
    steps: list[dict[str, Any]] | None = None,
    required_inputs: list[dict[str, Any]] | None = None,
    output_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scenario = resolve_scenario_label(preset_code, preset_name)
    resolved_steps = list(steps or DEFAULT_STEP_PROFILES.get(scenario, []))
    if not resolved_steps:
        resolved_steps = [{"code": "generate_documents", "title": "Генерация пакета"}]
    resolved_required_inputs = list(required_inputs or [])
    resolved_output_artifacts = list(
        output_artifacts
        or [
            {"kind": "zip", "title": f"{preset_name} bundle"},
            {"kind": "pdf", "title": f"{preset_name} summary"},
            {"kind": "manifest", "title": f"{preset_name} manifest"},
        ]
    )
    status_flow = ["draft", "running", "generated", "published"]
    return {
        "scenario": scenario,
        "steps": resolved_steps,
        "required_inputs": resolved_required_inputs,
        "output_artifacts": resolved_output_artifacts,
        "status_flow": status_flow,
        "pipeline_fingerprint": hashlib.sha256(
            json.dumps(
                {
                    "scenario": scenario,
                    "steps": resolved_steps,
                    "required_inputs": resolved_required_inputs,
                    "output_artifacts": resolved_output_artifacts,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }


@dataclass
class PackAssembler:
    template_id: str

    def assemble(
        self,
        packs: Iterable[DocumentPack],
        *,
        preset_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        shared_context = dict(context or {})
        assembled: list[dict[str, Any]] = []
        for index, pack in enumerate(packs, start=1):
            pack_context = {
                **shared_context,
                "pack": {
                    "name": pack.name,
                    "description": pack.description or "",
                    "sequence": index,
                    "preset_code": preset_code,
                },
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "template_id": self.template_id,
                        "preset_code": preset_code,
                        "index": index,
                        "name": pack.name,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            warnings = [] if pack.description else ["pack description is empty"]
            assembled.append(
                {
                    "name": pack.name,
                    "description": pack.description or "",
                    "template_id": self.template_id,
                    "preset_code": preset_code,
                    "sequence": index,
                    "context": pack_context,
                    "warnings": warnings,
                    "metadata": {"fingerprint": fingerprint, "warnings_count": len(warnings)},
                    "idempotency_key": f"{preset_code or 'pack'}:{self.template_id}:{index}:{pack.name}:{fingerprint[:12]}",
                }
            )
        return assembled
