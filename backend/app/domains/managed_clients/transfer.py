"""BIZ-49 срез-14 (разд. 49.1): правила переноса данных клиента в его арендатор.

Перевод (срез-13) переключает РЕЖИМ ведения; перенос — отдельная операция,
которая КОПИРУЕТ данные организации клиента из пространства аутсорсера в его
собственный арендатор. Чистые правила без БД:

* **перенос только после перевода.** Пока клиент Lightweight, у его данных
  один дом — пространство аутсорсера, и «переносить» их некуда;
* **перенос ровно один раз.** Повторный перенос создал бы в арендаторе
  клиента вторые копии всех людей — и различить их потом невозможно;
* **копия, а не переезд.** Исходные строки остаются историей в пространстве
  аутсорсера (решение среза-13: организация — ссылка на историю); аудит и
  timeline принципиально не переносятся — хеш-цепочка аудита живёт в своём
  арендаторе, и «переписать» её в чужой значит её сломать;
* **обезличенных и удалённых не переносят.** Обезличенная строка хранится по
  закону ИМЕННО там, где субъект работал (разд. 66.2); копия в новом
  арендаторе была бы новой обработкой ПДн без основания.
"""

from __future__ import annotations

from datetime import datetime

from app.domains.managed_clients.lifecycle import ManagedClientMode

__all__ = [
    "TransferError",
    "is_person_transferable",
    "validate_transfer_preconditions",
]


class TransferError(ValueError):
    """Перенос невозможен в текущем состоянии клиента."""


def validate_transfer_preconditions(
    *,
    mode: ManagedClientMode,
    dedicated_tenant_slug: str | None,
    company_id: str | None,
    has_completed_transfer: bool,
) -> None:
    if mode is not ManagedClientMode.DEDICATED or not dedicated_tenant_slug:
        raise TransferError(
            "Перенос доступен только после перевода клиента в собственный арендатор"
        )
    if not company_id:
        raise TransferError(
            "У клиента нет организации-истории в пространстве аутсорсера — переносить нечего"
        )
    if has_completed_transfer:
        raise TransferError("Данные клиента уже перенесены — повторный перенос создал бы дубли")


def is_person_transferable(*, deleted_at: datetime | None, anonymized_at: datetime | None) -> bool:
    """Кого копируем: только живые и не обезличенные записи."""

    return deleted_at is None and anonymized_at is None
