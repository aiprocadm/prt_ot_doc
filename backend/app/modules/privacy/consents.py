"""SEC-66 срез-2: согласия субъекта и обезличивание (разд. 66.1 и 66.2).

Два сервиса:

* :class:`PdnConsentService` — версионируемое хранение согласий и правовых
  оснований обработки. Согласия НЕ редактируются: перевыдача создаёт новую
  версию, отзыв помечает строку ``withdrawn``. Доказать правомерность прошлой
  обработки можно только по неизменной истории.
* :class:`PdnErasureService` — «удаление / отзыв согласия»: необратимое
  обезличивание прямых идентификаторов субъекта с сохранением записей, срок
  хранения которых предписан законом (обучение, медосмотры, СИЗ, инциденты).

Ключевая юридическая тонкость, ради которой основание хранится отдельным полем:
**отзыв согласия не обязывает стирать данные, обрабатываемые по другому
основанию** (трудовой договор, требование закона о сроках хранения по охране
труда). Поэтому отзыв и обезличивание — отдельные операции, а не одна: сервис
сообщает, какие основания остались, и решение принимает оператор.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_data import Person
from app.models.privacy_consents import (
    PDN_CONSENT_PURPOSES,
    PDN_LEGAL_BASES,
    PdnConsent,
    PdnErasureRecord,
)

__all__ = [
    "PdnConsentService",
    "PdnErasureService",
    "ErasureOutcome",
    "UnknownPurposeError",
    "UnknownLegalBasisError",
    "SCRUBBED_PERSON_FIELDS",
]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class UnknownPurposeError(ValueError):
    """Цель обработки вне справочника разд. 66.1."""


class UnknownLegalBasisError(ValueError):
    """Правовое основание вне справочника разд. 66.1."""


class PdnConsentService:
    """Версионируемые согласия субъекта (разд. 66.1)."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)

    async def list_for_subject(self, person_id: str) -> list[PdnConsent]:
        rows = (
            (
                await self.session.execute(
                    select(PdnConsent)
                    .where(
                        PdnConsent.tenant_id == self.tenant_id,
                        PdnConsent.subject_person_id == str(person_id),
                    )
                    .order_by(PdnConsent.purpose.asc(), PdnConsent.consent_version.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def active_for_subject(self, person_id: str) -> list[PdnConsent]:
        return [c for c in await self.list_for_subject(person_id) if c.status == "active"]

    async def grant(
        self,
        *,
        person_id: str,
        purpose: str,
        legal_basis: str = "consent",
        document_ref: str | None = None,
        text_sha256: str | None = None,
        expires_at: datetime | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> PdnConsent:
        """Выдать согласие. Прежняя версия по этой же цели уходит в ``superseded``."""

        if purpose not in PDN_CONSENT_PURPOSES:
            raise UnknownPurposeError(purpose)
        if legal_basis not in PDN_LEGAL_BASES:
            raise UnknownLegalBasisError(legal_basis)

        previous = (
            (
                await self.session.execute(
                    select(PdnConsent)
                    .where(
                        PdnConsent.tenant_id == self.tenant_id,
                        PdnConsent.subject_person_id == str(person_id),
                        PdnConsent.purpose == purpose,
                    )
                    .order_by(PdnConsent.consent_version.desc())
                )
            )
            .scalars()
            .all()
        )
        # Любая незакрытая версия становится superseded: «активная версия по цели»
        # должна быть ровно одна, иначе на вопрос «действует ли согласие» нет ответа.
        for row in previous:
            if row.status == "active":
                row.status = "superseded"
        next_version = (previous[0].consent_version + 1) if previous else 1

        consent = PdnConsent(
            tenant_id=self.tenant_id,
            subject_person_id=str(person_id),
            purpose=purpose,
            legal_basis=legal_basis,
            consent_version=next_version,
            status="active",
            document_ref=document_ref,
            text_sha256=text_sha256,
            expires_at=expires_at,
            granted_at=_utcnow(),
            recorded_by_user_id=str(actor_user_id) if actor_user_id else None,
            recorded_by_email=actor_email,
        )
        self.session.add(consent)
        await self.session.flush()
        return consent

    async def withdraw(
        self, *, person_id: str, purpose: str, reason: str | None = None
    ) -> PdnConsent | None:
        """Отозвать действующее согласие по цели. Строка не удаляется."""

        consent = (
            await self.session.execute(
                select(PdnConsent)
                .where(
                    PdnConsent.tenant_id == self.tenant_id,
                    PdnConsent.subject_person_id == str(person_id),
                    PdnConsent.purpose == purpose,
                    PdnConsent.status == "active",
                )
                .order_by(PdnConsent.consent_version.desc())
            )
        ).scalar_one_or_none()
        if consent is None:
            return None
        consent.status = "withdrawn"
        consent.withdrawn_at = _utcnow()
        consent.withdrawal_reason = reason
        await self.session.flush()
        return consent

    async def remaining_legal_bases(self, person_id: str) -> list[str]:
        """Основания, по которым обработка остаётся правомерной после отзыва.

        Пусто → обрабатывать субъекта больше не на чем, и обезличивание становится
        обязанностью, а не опцией.
        """

        active = await self.active_for_subject(person_id)
        return sorted({c.legal_basis for c in active})


# Прямые идентификаторы, вычищаемые при обезличивании, и чем они заменяются.
# ``hired_at`` и ``birth_date`` тоже уходят: в маленькой компании дата приёма плюс
# должность и подразделение восстанавливают личность, а закон требует хранить
# ФАКТ обучения/медосмотра, а не дату найма конкретного человека.
SCRUBBED_PERSON_FIELDS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "middle_name",
    "birth_date",
    "email",
    "phone",
    "personnel_number",
    "snils",
    "passport",
    "hired_at",
    "qualifications",
    "current_ppe",
    "ppe_sizes",
)


@dataclass(frozen=True)
class ErasureOutcome:
    """Что сделали и что осталось — ответ субъекту и проверяющему."""

    record: PdnErasureRecord
    already_anonymized: bool


class PdnErasureService:
    """«Удаление / отзыв согласия»: обезличивание субъекта (разд. 66.2)."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)

    async def existing_record(self, person_id: str) -> PdnErasureRecord | None:
        return (
            await self.session.execute(
                select(PdnErasureRecord)
                .where(
                    PdnErasureRecord.tenant_id == self.tenant_id,
                    PdnErasureRecord.subject_person_id == str(person_id),
                )
                .order_by(PdnErasureRecord.performed_at.desc())
            )
        ).scalar_one_or_none()

    async def anonymize(
        self,
        person: Person,
        *,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> ErasureOutcome:
        """Необратимо вычистить прямые идентификаторы, сохранив связанные записи.

        Идемпотентно: повторный вызов не «доочищает» и не плодит записи, а
        возвращает уже существующую — повтор запроса субъекта не должен выглядеть
        как второе, другое обезличивание.
        """

        if person.anonymized_at is not None:
            existing = await self.existing_record(str(person.id))
            if existing is not None:
                return ErasureOutcome(record=existing, already_anonymized=True)

        pseudonym = f"subject-{uuid.uuid4().hex[:12]}"
        scrubbed: dict[str, bool] = {}
        for field in SCRUBBED_PERSON_FIELDS:
            had_value = bool(getattr(person, field, None))
            scrubbed[field] = had_value

        person.first_name = "Обезличено"
        person.last_name = pseudonym
        person.middle_name = None
        person.birth_date = None
        person.email = None
        person.phone = None
        # personnel_number участвует в UNIQUE(tenant_id, personnel_number); NULL
        # не конфликтует, поэтому обезличивание не может упасть на дубликате.
        person.personnel_number = None
        person.snils = None
        person.passport = None
        person.hired_at = None
        person.qualifications = []
        person.current_ppe = []
        person.ppe_sizes = None
        person.anonymized_at = _utcnow()

        retained = await self._retained_sections(str(person.id))

        record = PdnErasureRecord(
            tenant_id=self.tenant_id,
            subject_person_id=str(person.id),
            pseudonym=pseudonym,
            reason=reason,
            scrubbed_fields=scrubbed,
            retained_sections=retained,
            performed_at=_utcnow(),
            performed_by_user_id=str(actor_user_id) if actor_user_id else None,
            performed_by_email=actor_email,
        )
        self.session.add(record)
        await self.session.flush()
        return ErasureOutcome(record=record, already_anonymized=False)

    async def _retained_sections(self, person_id: str) -> dict[str, int]:
        """Сколько записей осталось обезличенными — доказательство сохранности.

        Считается прямыми COUNT'ами по таблицам, привязанным к субъекту: строить
        ради счётчиков полную карточку сотрудника (десятки запросов, лимиты на
        секцию) здесь незачем, а числа нужны точные, а не усечённые.
        """

        from app.models.models import MedicalExam, PPEIssue
        from app.models.training import TrainingSession

        counts: dict[str, int] = {}
        for name, model in (
            ("medical_exams", MedicalExam),
            ("ppe_issues", PPEIssue),
            ("training_sessions", TrainingSession),
        ):
            total = (
                await self.session.execute(
                    select(func.count())
                    .select_from(model)
                    .where(
                        model.tenant_id == self.tenant_id,
                        model.person_id == person_id,
                    )
                )
            ).scalar_one()
            counts[name] = int(total)
        return counts
