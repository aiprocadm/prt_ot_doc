"""Отправка в ЭДО: шов к оператору и рабочая выгрузка пакета (BIZ-50, разд. 50.2).

ЧТО БЫЛО. ``POST /edo/send`` заканчивался ``_provider_not_configured("edo")`` —
честный отказ вместо симуляции, и это было правильное решение своего времени.
Но строка матрицы держала в остатке «отправка в ЭДО (после реализации
провайдера)», то есть ручка оставалась ЗАВЕДОМЫМ ТУПИКОМ: что бы ни настроил
владелец, кода для отправки не существовало.

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Три поставщика вместо одного
отказа:

* ``disabled`` — умолчание, прежнее поведение (409). Ничего не ломается у тех,
  кто ЭДО не подключал.
* ``file`` — **рабочая выгрузка без всякого оператора.** Собирается настоящий
  ZIP: сам файл документа, опись и записи о подписях. Так и работает практика
  там, где оператора нет: пакет выгружают и передают получателю.
* ``command`` — пакет отдаётся внешней команде (CLI оператора, http-обёртка).
  Тот же приём, что у хранилища ключей и SMS, и по той же причине.

ЧЕСТНОСТЬ ФОРМУЛИРОВОК — ГЛАВНОЕ ЗДЕСЬ. Выгрузка файлом означает «пакет
собран», а НЕ «получатель принял». Поэтому провайдер ``file`` ставит сообщению
статус ``sent`` и пишет в ответе, что пакет надо передать получателю. Ставить
``delivered`` или ``accepted`` было бы ровно тем, за что платформа уже платила:
адаптер, уверяющий, что ведомство приняло данные.

АРХИВ НАСТОЯЩИЙ. В истории репозитория есть прямое предупреждение: раньше в
хранилище клали строку «ZIP bundle for …» с типом ``application/zip``, и клиент
скачивал файл, который не открывается ни одним архиватором. Здесь ZIP
собирается ``zipfile``, а файл документа берётся из хранилища; если файла нет —
это отказ, а не архив с описью и без документа.
"""

from __future__ import annotations

import io
import json
import logging
import shlex
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DISABLED_PROVIDER = "disabled"
FILE_PROVIDER = "file"
COMMAND_PROVIDER = "command"
KNOWN_PROVIDERS = (DISABLED_PROVIDER, FILE_PROVIDER, COMMAND_PROVIDER)

#: Код провайдера, попадающий в сообщение и в ответ ручки. Намеренно говорящий:
#: читающий журнал должен видеть, что это выгрузка, а не оператор.
FILE_PROVIDER_CODE = "file-export"

DEFAULT_TIMEOUT_SECONDS = 60.0


class EdoDispatchError(RuntimeError):
    """Отправить не удалось. Сообщение предназначено человеку."""


@dataclass(frozen=True)
class EdoPackage:
    """Что именно уходит в ЭДО."""

    document_version_id: str
    file_key: str
    file_name: str
    recipient: str | None = None
    operator_code: str | None = None
    signatures: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class EdoDispatchResult:
    provider_code: str
    external_id: str
    status: str
    detail: str
    artifact_key: str | None = None


def provider_name(settings) -> str:
    raw = (getattr(settings, "edo_provider", "") or DISABLED_PROVIDER).strip().lower()
    return raw if raw in KNOWN_PROVIDERS else DISABLED_PROVIDER


def build_manifest(package: EdoPackage, *, tenant_id: str, now: datetime | None = None) -> dict:
    """Опись пакета. Отдельно от сборки архива — чтобы проверять без хранилища."""

    moment = now or datetime.now(tz=timezone.utc)
    return {
        "format": "ptd-edo-package/1",
        "tenant_id": tenant_id,
        "document_version_id": package.document_version_id,
        "document_file": package.file_name,
        "recipient": package.recipient,
        "operator_code": package.operator_code,
        "signatures": package.signatures,
        "built_at": moment.isoformat(),
        # Прямая оговорка внутри самого пакета: выгрузка ≠ доставка.
        "note": (
            "Пакет выгружен платформой. Факт получения адресатом здесь НЕ "
            "подтверждается: передайте пакет получателю выбранным способом."
        ),
    }


def build_archive(package: EdoPackage, *, tenant_id: str, document_bytes: bytes) -> bytes:
    """Собрать НАСТОЯЩИЙ ZIP: документ, опись, записи о подписях."""

    if not document_bytes:
        # Архив с описью и без документа выглядел бы как успешная выгрузка.
        raise EdoDispatchError(
            "Файл документа пуст или недоступен в хранилище — собирать пакет не из чего"
        )

    manifest = build_manifest(package, tenant_id=tenant_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(package.file_name, document_bytes)
        archive.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        )
        for index, signature in enumerate(package.signatures, start=1):
            archive.writestr(
                f"signatures/{index:02d}.json",
                json.dumps(signature, ensure_ascii=False, indent=2).encode("utf-8"),
            )
    return buffer.getvalue()


def dispatch_via_command(archive_bytes: bytes, *, package: EdoPackage, settings) -> str:
    """Отдать пакет внешней команде. Возвращает идентификатор у оператора.

    Команда получает архив в стандартный ввод и печатает идентификатор
    отправления в стандартный вывод. Пустой ответ — отказ: без идентификатора
    отследить судьбу отправления нельзя, а «отправлено неизвестно что» хуже,
    чем честная ошибка.
    """

    command = (getattr(settings, "edo_command", "") or "").strip()
    if not command:
        raise EdoDispatchError("EDO_PROVIDER=command требует EDO_COMMAND")

    timeout = float(
        getattr(settings, "edo_command_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        or DEFAULT_TIMEOUT_SECONDS
    )
    args = shlex.split(command)
    if package.recipient:
        args.append(package.recipient)
    try:
        completed = subprocess.run(  # noqa: S603 - команда задаётся администратором
            args, input=archive_bytes, capture_output=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise EdoDispatchError(f"EDO_COMMAND не запускается: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise EdoDispatchError(f"Оператор ЭДО не ответил за {timeout:g} с") from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", "replace").strip()[:300]
        raise EdoDispatchError(
            f"Оператор ЭДО отклонил пакет (код {completed.returncode})"
            + (f": {stderr}" if stderr else "")
        )

    external_id = (completed.stdout or b"").decode("utf-8", "replace").strip()
    if not external_id:
        raise EdoDispatchError(
            "Оператор ЭДО не вернул идентификатор отправления — отследить его будет нечем"
        )
    return external_id[:255]


__all__ = [
    "COMMAND_PROVIDER",
    "DISABLED_PROVIDER",
    "FILE_PROVIDER",
    "FILE_PROVIDER_CODE",
    "KNOWN_PROVIDERS",
    "EdoDispatchError",
    "EdoDispatchResult",
    "EdoPackage",
    "build_archive",
    "build_manifest",
    "dispatch_via_command",
    "provider_name",
]
