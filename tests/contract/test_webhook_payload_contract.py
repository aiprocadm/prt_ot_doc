"""OPS-73 срез-2 (разд. 73.3): «событие тоже контракт» — гейт вебхук-payload'ов.

REST-контракт стережёт OpenAPI-гейт; у событий такой опоры не было: убрать поле
из payload-модели или целый тип события можно было незаметно — подписчик узнал
бы из своего упавшего парсера.

Здесь v1-контракт ЗАМОРОЖЕН явным перечислением:

* конверты ОБОИХ конвейеров доставки (их два, и они разные — историческая
  правда, слить = ломающее изменение) обязаны нести перечисленные ключи и
  ``schema_version``;
* список типов событий — удаление типа ломает подписчиков; добавление законно;
* поля payload-модели КАЖДОГО типа — удаление или переименование поля ломает
  подписчиков; добавление законно (разд. 73.1: «добавления — в текущей»).

Правило работы с гейтом: расширили модель — тест зелёный, ничего делать не
надо; сузили — либо это ошибка, либо сознательное ломающее изменение, и тогда
поднимайте ``WEBHOOK_SCHEMA_VERSION`` и правьте замороженную карту В ОДНОМ PR
со строкой в CHANGELOG (это и есть «анонс» для подписчиков).
"""

from __future__ import annotations

import pytest

from app.core.webhook_contract import (
    DISPATCHER_ENVELOPE_KEYS,
    OUTBOX_TASK_BODY_KEYS,
    WEBHOOK_SCHEMA_VERSION,
)
from app.services.events import _PAYLOADS, EventType

pytestmark = pytest.mark.contract

# --- замороженный v1-контракт ---------------------------------------------

FROZEN_EVENT_TYPES = {
    "DocumentCreated",
    "DocumentGenerated",
    "DocumentSigned",
    "Signed",
    "DocumentExported",
    "Exported",
    "RiskAssessed",
    "PPEIssued",
    "PPEReturned",
    "TrainingCompleted",
    "TrainingAssigned",
    "TaskDueSoon",
    "TaskOverdue",
    "approval.started",
    "approval.decision_made",
    "approval.completed",
    "edo.sent",
    "edo.status_changed",
    "IncidentCreated",
    "InspectionCreated",
    "PrescriptionOverdue",
    "MedicalExamRecorded",
    "PersonSuspended",
    "PersonReinstated",
    "contractor.readiness_blocked",
    "contractor.readiness_warning",
    "contractor.document_expiring",
    "contractor.document_expired",
    "PPEWrittenOff",
    "PPEReplacementDue",
    "PEPSigned",
    "PEPDeclined",
    "rule.triggered",
}

_INTERNAL = ["actor_id", "event_id", "metadata", "occurred_at", "tenant_id"]

FROZEN_PAYLOAD_FIELDS: dict[str, list[str]] = {
    "DocumentCreated": [
        "actor_id",
        "company_id",
        "document_id",
        "document_version_id",
        "event_id",
        "occurred_at",
        "person_id",
        "status",
        "storage_key",
        "template_id",
        "template_version_id",
        "tenant_id",
    ],
    "DocumentExported": [
        "actor_id",
        "documents",
        "event_id",
        "occurred_at",
        "pack_code",
        "pack_id",
        "tenant_id",
        "zip_storage_key",
    ],
    "DocumentGenerated": [
        "actor_id",
        "company_id",
        "document_id",
        "document_version_id",
        "event_id",
        "occurred_at",
        "person_id",
        "status",
        "storage_key",
        "template_id",
        "template_version_id",
        "tenant_id",
    ],
    "DocumentSigned": [
        "actor_id",
        "document_id",
        "document_version_id",
        "event_id",
        "occurred_at",
        "signed_at",
        "signed_file_id",
        "status",
        "tenant_id",
    ],
    "Exported": [
        "actor_id",
        "documents",
        "event_id",
        "occurred_at",
        "pack_code",
        "pack_id",
        "tenant_id",
        "zip_storage_key",
    ],
    "IncidentCreated": [
        "actor_id",
        "company_id",
        "event_id",
        "incident_id",
        "incident_type",
        "occurred_at",
        "severity",
        "site_id",
        "status",
        "tenant_id",
    ],
    "InspectionCreated": [
        "actor_id",
        "authority",
        "company_id",
        "event_id",
        "inspection_id",
        "inspection_type",
        "occurred_at",
        "site_id",
        "status",
        "tenant_id",
    ],
    "MedicalExamRecorded": [
        "actor_id",
        "event_id",
        "exam_id",
        "exam_kind",
        "fitness",
        "occurred_at",
        "person_id",
        "tenant_id",
        "valid_until",
    ],
    "PEPDeclined": [
        "actor_id",
        "event_id",
        "occurred_at",
        "reason",
        "signature_request_id",
        "tenant_id",
    ],
    "PEPSigned": [
        "actor_id",
        "event_id",
        "object_id",
        "object_type",
        "occurred_at",
        "purpose",
        "signature_request_id",
        "signer_person_id",
        "signer_user_id",
        "tenant_id",
    ],
    "PPEIssued": [
        "actor_id",
        "event_id",
        "expires_at",
        "issued_at",
        "item_id",
        "occurred_at",
        "person_id",
        "ppe_issue_id",
        "quantity",
        "status",
        "tenant_id",
    ],
    "PPEReplacementDue": [
        "actor_id",
        "event_id",
        "expires_at",
        "item_id",
        "item_name",
        "occurred_at",
        "person_id",
        "ppe_issue_id",
        "status",
        "tenant_id",
    ],
    "PPEReturned": [
        "actor_id",
        "event_id",
        "item_id",
        "occurred_at",
        "person_id",
        "ppe_issue_id",
        "quantity",
        "returned_at",
        "status",
        "tenant_id",
    ],
    "PPEWrittenOff": [
        "actor_id",
        "event_id",
        "item_id",
        "occurred_at",
        "person_id",
        "ppe_issue_id",
        "quantity",
        "reason",
        "status",
        "tenant_id",
    ],
    "PersonReinstated": [
        "actor_id",
        "event_id",
        "occurred_at",
        "person_id",
        "suspension_id",
        "tenant_id",
    ],
    "PersonSuspended": [
        "actor_id",
        "event_id",
        "occurred_at",
        "person_id",
        "reason",
        "source_exam_id",
        "suspension_id",
        "tenant_id",
    ],
    "PrescriptionOverdue": [
        "actor_id",
        "assignee_id",
        "due_at",
        "event_id",
        "incident_id",
        "inspection_id",
        "occurred_at",
        "prescription_id",
        "status",
        "tenant_id",
    ],
    "RiskAssessed": [
        "action_plan",
        "actor_id",
        "after",
        "before",
        "company_id",
        "controls",
        "document_pack_id",
        "event_id",
        "hazard_code",
        "occurred_at",
        "place_id",
        "position_id",
        "risk_assessment_id",
        "tenant_id",
    ],
    "Signed": [
        "actor_id",
        "document_id",
        "document_version_id",
        "event_id",
        "occurred_at",
        "signed_at",
        "signed_file_id",
        "status",
        "tenant_id",
    ],
    "TaskDueSoon": [
        "actor_id",
        "assignee_id",
        "due_at",
        "event_id",
        "occurred_at",
        "overdue",
        "priority",
        "status",
        "task_id",
        "tenant_id",
        "title",
    ],
    "TaskOverdue": [
        "actor_id",
        "assignee_id",
        "due_at",
        "event_id",
        "occurred_at",
        "overdue",
        "priority",
        "status",
        "task_id",
        "tenant_id",
        "title",
    ],
    "TrainingAssigned": [
        "actor_id",
        "assigned_at",
        "company_id",
        "course_id",
        "due_date",
        "event_id",
        "is_mandatory",
        "occurred_at",
        "person_id",
        "plan_id",
        "position_id",
        "tenant_id",
        "training_event_id",
    ],
    "TrainingCompleted": [
        "actor_id",
        "completed_at",
        "course_id",
        "event_id",
        "occurred_at",
        "person_id",
        "plan_id",
        "score",
        "session_id",
        "status",
        "tenant_id",
        "training_event_id",
    ],
    "approval.completed": _INTERNAL,
    "approval.decision_made": _INTERNAL,
    "approval.started": _INTERNAL,
    "contractor.document_expired": _INTERNAL,
    "contractor.document_expiring": _INTERNAL,
    "contractor.readiness_blocked": _INTERNAL,
    "contractor.readiness_warning": _INTERNAL,
    "edo.sent": _INTERNAL,
    "edo.status_changed": _INTERNAL,
    "rule.triggered": [
        "actor_id",
        "event_id",
        "occurred_at",
        "rule_id",
        "rule_name",
        "source_event_key",
        "source_event_type",
        "source_payload",
        "tenant_id",
    ],
}


class TestEventCatalogue:
    def test_no_event_type_disappears(self) -> None:
        """Удаление типа события — ломающее изменение для его подписчиков."""

        current = {e.value for e in EventType}
        removed = sorted(FROZEN_EVENT_TYPES - current)

        assert not removed, "Типы событий исчезли без bump'а WEBHOOK_SCHEMA_VERSION: " + ", ".join(
            removed
        )

    def test_every_event_type_has_a_payload_model(self) -> None:
        """Тип без модели — payload без валидации и без контракта вовсе."""

        unmapped = sorted({e.value for e in EventType} - {e.value for e in _PAYLOADS})

        assert not unmapped, "Типы без payload-модели: " + ", ".join(unmapped)


class TestPayloadFields:
    def test_no_payload_field_disappears(self) -> None:
        """Удаление/переименование поля payload ломает парсер подписчика.

        Добавление полей законно и гейт его пропускает: замороженная карта —
        это МИНИМУМ v1, а не точный слепок.
        """

        by_value = {e.value: m for e, m in _PAYLOADS.items()}
        problems: list[str] = []
        for event_value, frozen_fields in FROZEN_PAYLOAD_FIELDS.items():
            model = by_value.get(event_value)
            if model is None:
                continue  # исчезновение типа ловит соседний тест
            current = set(model.model_fields)
            for field in frozen_fields:
                if field not in current:
                    problems.append(f"{event_value}.{field}")

        assert not problems, (
            "Поля payload исчезли без bump'а WEBHOOK_SCHEMA_VERSION "
            "(remove_field/rename_field из API_BREAKING_CHANGES): " + ", ".join(problems[:20])
        )

    def test_frozen_map_covers_every_frozen_event(self) -> None:
        """Карта полей обязана покрывать каждый замороженный тип — иначе у гейта
        слепые зоны, которые выглядят как покрытие."""

        missing = sorted(FROZEN_EVENT_TYPES - set(FROZEN_PAYLOAD_FIELDS))

        assert not missing, "Типы без замороженных полей: " + ", ".join(missing)


class TestEnvelopes:
    def test_dispatcher_envelope_carries_the_contract_keys(self) -> None:
        """Конверт конвейера подписок собирается ровно из ключей контракта."""

        import inspect

        from app.services.webhooks import WebhookDispatcher

        source = inspect.getsource(WebhookDispatcher.dispatch)
        for key in DISPATCHER_ENVELOPE_KEYS:
            assert f'"{key}"' in source, f"конверт dispatcher потерял ключ {key!r}"

    def test_outbox_task_body_carries_the_contract_keys(self) -> None:
        """Тело конвейера очереди собирается ровно из ключей контракта."""

        import inspect

        from app.tasks import _core

        source = inspect.getsource(_core._dispatch_outbox_events)
        for key in OUTBOX_TASK_BODY_KEYS:
            assert f'"{key}"' in source, f"тело outbox-доставки потеряло ключ {key!r}"

    def test_schema_version_is_one_until_a_breaking_change(self) -> None:
        assert WEBHOOK_SCHEMA_VERSION == "1", (
            "Версия схемы поднята — убедитесь, что замороженные карты в этом файле "
            "обновлены и строка-анонс добавлена в CHANGELOG"
        )
