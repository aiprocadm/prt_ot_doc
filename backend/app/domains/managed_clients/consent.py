"""BIZ-49 срез-12 (Доп. №1 разд. 49.3 + Доп. №3 разд. 66.3): согласие клиента.

Аутсорсер обрабатывает ПДн сотрудников клиента, и по 152-ФЗ на это нужны
«согласия/поручения по цепочке» (разд. 66.3). До этого среза платформа
позволяла выдать специалисту доступ к данным клиента, не спросив самого
клиента, — юридическое основание держалось «где-то в папке у юриста», и на
вопрос проверяющего «на каком основании ваш специалист смотрел эти данные»
платформа ответить не могла.

Чистые правила без БД. Решения, которые нельзя отдать интерфейсу:

* **без активного согласия доступ не выдаётся и контекст не открывается.**
  Проверка стоит в ДВУХ местах: выдача гранта и вход «от имени». Одной первой
  мало — гранты долгоживущие, и согласие может быть отозвано позже выдачи;
* **отзыв — момент времени, а не удаление строки** (тот же принцип, что у
  грантов, срез-6): «действовало ли согласие, когда специалист работал» —
  вопрос, на который платформа обязана отвечать и после отзыва;
* **реквизиты документа-основания обязательны.** Согласие «на словах» не
  основание: строка без ссылки на документ не поможет ни аудитору, ни юристу;
* **истёкшее согласие равно отозванному.** Срок в документе — часть
  волеизъявления клиента, продлевать его молча платформа не вправе.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

__all__ = [
    "ClientConsent",
    "ConsentInvalid",
    "ConsentRequired",
    "active_consent",
    "is_consent_active",
    "require_active_consent",
    "validate_consent",
]


class ConsentRequired(ValueError):
    """У клиента нет действующего согласия на делегированный доступ."""


class ConsentInvalid(ValueError):
    """Согласие противоречиво и не может быть записано."""


@dataclass(frozen=True)
class ClientConsent:
    client_id: str
    document_ref: str
    granted_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


def validate_consent(
    *, document_ref: str, granted_at: datetime, expires_at: datetime | None
) -> None:
    """Проверить намерение до записи."""

    if not document_ref.strip():
        raise ConsentInvalid(
            "Согласие обязано ссылаться на документ-основание (номер поручения/согласия)"
        )
    if expires_at is not None and expires_at <= granted_at:
        raise ConsentInvalid("Срок согласия не может истекать раньше его выдачи")


def _as_utc(value: datetime) -> datetime:
    """Нормализовать момент к UTC.

    Из базы дата может прийти БЕЗ часового пояса (SQLite и часть драйверов),
    а сравнение naive с aware падает TypeError — урок среза-6: проверка
    доступа не имеет права ронять запрос из-за формата хранения времени.
    """

    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_consent_active(consent: ClientConsent, *, now: datetime) -> bool:
    """Действует ли согласие в момент ``now``."""

    moment = _as_utc(now)
    if consent.revoked_at is not None and _as_utc(consent.revoked_at) <= moment:
        return False
    if consent.expires_at is not None and _as_utc(consent.expires_at) <= moment:
        return False
    return True


def active_consent(
    consents: list[ClientConsent] | tuple[ClientConsent, ...], *, now: datetime
) -> ClientConsent | None:
    """Первое действующее согласие или ``None``."""

    for consent in consents:
        if is_consent_active(consent, now=now):
            return consent
    return None


def require_active_consent(
    consents: list[ClientConsent] | tuple[ClientConsent, ...], *, now: datetime
) -> ClientConsent:
    """Действующее согласие обязательно — иначе ``ConsentRequired``."""

    consent = active_consent(consents, now=now)
    if consent is None:
        raise ConsentRequired(
            "У клиента нет действующего согласия на делегированный доступ (разд. 66)"
        )
    return consent
