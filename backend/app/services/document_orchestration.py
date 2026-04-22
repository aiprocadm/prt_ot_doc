from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ORCHESTRATION_STATES: tuple[str, ...] = (
    "generated",
    "headers_applied",
    "pdf_ready",
    "handoff_ready",
    "failed",
    "retrying",
)

_USER_FACING_ERRORS: dict[str, str] = {
    "template version payload is missing": "У версии шаблона отсутствует DOCX-файл. Загрузите файл и повторите запуск.",
    "template version not found": "Версия шаблона не найдена. Проверьте, что версия активна.",
    "template not found": "Шаблон не найден. Проверьте код и версию шаблона.",
    "company not found": "Компания не найдена или недоступна в текущем tenant.",
    "person not found": "Карточка сотрудника не найдена или недоступна.",
    "person does not belong to company": "Сотрудник не относится к выбранной компании.",
    "initiating user not found": "Пользователь-инициатор не найден. Выполните запуск повторно.",
}


def init_orchestration(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.setdefault("state", "generated")
    payload.setdefault("timeline", [])
    payload.setdefault("retry_count", 0)
    return payload


def set_state(
    metadata: dict[str, Any] | None,
    *,
    state: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in ORCHESTRATION_STATES:
        raise ValueError(f"unsupported orchestration state: {state}")

    orchestration = init_orchestration(metadata)
    orchestration["state"] = state
    if details:
        orchestration.setdefault("details", {}).update(details)
    timeline = list(orchestration.get("timeline") or [])
    if not timeline or timeline[-1].get("state") != state:
        timeline.append(
            {
                "state": state,
                "at": datetime.now(tz=timezone.utc).isoformat(),
                "details": details or {},
            }
        )
    orchestration["timeline"] = timeline
    return orchestration


def normalize_user_facing_error(raw_error: str | None) -> str | None:
    if not raw_error:
        return None
    lowered = raw_error.strip().lower()
    for key, message in _USER_FACING_ERRORS.items():
        if key in lowered:
            return message
    return "Не удалось завершить генерацию документа. Проверьте шаблон, данные и повторите запуск."
