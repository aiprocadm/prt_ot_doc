"""PEP signing service (vNext §6.9): session-aware оркестрация чистого домена.

Создание/подтверждение/отклонение запросов ПЭП, построение канонического
payload по типу объекта, гейт согласования (Task 5), диспетчер потребителей
на signed (Task 5), outbox-события.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.signing.pep import (
    CONFIRM_TTL_MINUTES,
    PEP_PURPOSES,
    ConfirmOutcome,
    InvalidTransition,
    PepStatus,
    assert_transition,
    canonical_payload,
    confirm_outcome,
    content_hash,
    hash_confirm_code,
)
from app.models.approval_workflow import ApprovalInstanceStatus
from app.models.document import DocumentVersion
from app.models.models import ApprovalInstance, BriefingEntry, Person, PPEIssue, SignatureRequest
from app.models.work_permit import WorkPermit, WorkPermitBriefing, WorkPermitMember
from app.services.events import EventType
from app.services.outbox import OutboxService


class PepNotFound(LookupError):
    """Объект/запрос не найден (или чужой тенант)."""


class PepConflict(ValueError):
    """Бизнес-конфликт: дубль, неверный/истёкший код, недопустимый переход."""


class PepApprovalRequired(PepConflict):
    """Гейт согласования не пройден: документ не APPROVED.

    Подкласс PepConflict — существующие except PepConflict продолжают ловить
    его; API-слой маппит отдельно в 409 code="PEP_APPROVAL_REQUIRED".
    """


class PepForbidden(PermissionError):
    """Авторизационный отказ: только назначенный подписант может подтвердить запрос."""


_ACTIVE_STATUSES = (PepStatus.CREATED.value, PepStatus.AWAITING_CODE.value)


class PepSigningService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self._outbox = OutboxService(self.session)

    # --- payload builders -------------------------------------------------

    async def _build_content(self, object_type: str, object_id: str) -> dict[str, Any]:
        if object_type == "document_version":
            doc = await self.session.get(DocumentVersion, object_id)
            if doc is None or str(doc.tenant_id) != str(self.tenant_id):
                raise PepNotFound("document_version")
            return {
                "document_id": doc.document_id,
                "document_version_id": doc.id,
                "version_number": doc.version_number,
                "file_key": doc.file_key,
            }
        if object_type == "ppe_issue":
            issue = await self.session.get(PPEIssue, object_id)
            if issue is None or str(issue.tenant_id) != str(self.tenant_id):
                raise PepNotFound("ppe_issue")
            return {
                "ppe_issue_id": issue.id,
                "person_id": issue.person_id,
                "item_id": issue.item_id,
                "item_name": issue.item_name,
                "quantity": issue.quantity,
                "status": issue.status,
                "issued_at": issue.issued_at.isoformat() if issue.issued_at else None,
            }
        if object_type == "briefing_entry":
            entry = await self.session.get(BriefingEntry, object_id)
            if entry is None or str(entry.tenant_id) != str(self.tenant_id):
                raise PepNotFound("briefing_entry")
            return {
                "briefing_entry_id": entry.id,
                "person_id": entry.person_id,
                "briefing_template_id": entry.briefing_template_id,
                "briefing_date": entry.briefing_date.isoformat() if entry.briefing_date else None,
            }
        if object_type == "work_permit":
            wp = await self.session.get(WorkPermit, object_id)
            if wp is None or str(wp.tenant_id) != str(self.tenant_id):
                raise PepNotFound("work_permit")
            members = (
                await self.session.execute(
                    select(WorkPermitMember)
                    .where(
                        WorkPermitMember.tenant_id == self.tenant_id,
                        WorkPermitMember.work_permit_id == wp.id,
                    )
                    .order_by(WorkPermitMember.created_at.asc())
                )
            ).scalars().all()
            return {
                "work_permit_id": wp.id,
                "number": wp.number,
                "work_type": wp.work_type,
                "zone_text": wp.zone_text,
                "status": wp.status,
                "members": [{"person_id": m.person_id, "role": m.role} for m in members],
            }
        if object_type == "work_permit_briefing":
            br = await self.session.get(WorkPermitBriefing, object_id)
            if br is None or str(br.tenant_id) != str(self.tenant_id):
                raise PepNotFound("work_permit_briefing")
            return {
                "work_permit_briefing_id": br.id,
                "work_permit_id": br.work_permit_id,
                "conducted_by_person_id": br.conducted_by_person_id,
                "conducted_at": br.conducted_at.isoformat() if br.conducted_at else None,
                "topics_text": br.topics_text,
            }
        if object_type == "work_permit_closing":
            wp = await self.session.get(WorkPermit, object_id)
            if wp is None or str(wp.tenant_id) != str(self.tenant_id):
                raise PepNotFound("work_permit")
            return {
                "work_permit_closing_id": wp.id,
                "work_permit_id": wp.id,
                "number": wp.number,
                "completion_text": wp.completion_text,
                "completion_recorded_at": (
                    wp.completion_recorded_at.isoformat() if wp.completion_recorded_at else None
                ),
                "status": wp.status,
            }
        raise PepConflict(f"unsupported object_type: {object_type}")

    async def _signer_name(
        self,
        *,
        signer_user_id: str | None,
        signer_person_id: str | None,
    ) -> str | None:
        if signer_person_id:
            person = await self.session.get(Person, signer_person_id)
            if person is None or str(person.tenant_id) != str(self.tenant_id):
                raise PepNotFound("person")
            parts = [person.last_name, person.first_name, person.middle_name or ""]
            return " ".join(p for p in parts if p).strip()
        # TODO: display name пользователя — внешний auth-контур; пока сырой id
        return signer_user_id

    # --- lifecycle ---------------------------------------------------------

    async def create_request(
        self,
        *,
        object_type: str,
        object_id: str,
        purpose: str,
        requested_by: str,
        signer_user_id: str | None = None,
        signer_person_id: str | None = None,
    ) -> tuple[SignatureRequest, str | None]:
        """Возвращает (запрос, разовый код | None). Код виден только здесь."""
        if purpose not in PEP_PURPOSES:
            raise PepConflict(f"unsupported purpose: {purpose}")
        if bool(signer_user_id) == bool(signer_person_id):
            raise PepConflict("exactly one of signer_user_id / signer_person_id is required")

        content = await self._build_content(object_type, object_id)
        await self._approval_gate(object_type, object_id, purpose)

        signer_filter = (
            SignatureRequest.signer_user_id == signer_user_id
            if signer_user_id
            else SignatureRequest.signer_person_id == signer_person_id
        )
        dup = (
            await self.session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == self.tenant_id,
                    SignatureRequest.object_type == object_type,
                    SignatureRequest.object_id == object_id,
                    SignatureRequest.purpose == purpose,
                    SignatureRequest.status.in_(_ACTIVE_STATUSES),
                    signer_filter,
                )
            )
        ).scalars().first()
        if dup is not None:
            raise PepConflict("active pep request already exists for this signer/object")

        payload = canonical_payload(object_type, object_id, content)
        req = SignatureRequest(
            tenant_id=self.tenant_id,
            object_type=object_type,
            object_id=object_id,
            provider="internal",
            provider_code="internal",
            signature_type="pep",
            purpose=purpose,
            requested_by=requested_by,
            signer_user_id=signer_user_id,
            signer_person_id=signer_person_id,
            content_hash=content_hash(payload),
            payload_json={"canonical": payload},
            status=PepStatus.CREATED.value,
        )
        self.session.add(req)
        await self.session.flush()

        code: str | None = None
        if signer_person_id:
            code = f"{secrets.randbelow(1_000_000):06d}"
            req.confirm_code_hash = hash_confirm_code(req.id, code)
            req.confirm_code_expires_at = (
                datetime.now(tz=timezone.utc) + timedelta(minutes=CONFIRM_TTL_MINUTES)
            )
            assert_transition(PepStatus.CREATED, PepStatus.AWAITING_CODE)
            req.status = PepStatus.AWAITING_CODE.value
            await self.session.flush()
        elif signer_user_id == requested_by:
            await self._mark_signed(req)
        # else: чужой user-подписант подтверждает сам через confirm(code=None)
        return req, code

    async def _get_own(self, request_id: str) -> SignatureRequest:
        req = await self.session.get(SignatureRequest, request_id)
        if req is None or str(req.tenant_id) != str(self.tenant_id) or req.signature_type != "pep":
            raise PepNotFound("signature_request")
        return req

    async def confirm(
        self,
        request_id: str,
        *,
        code: str | None = None,
        acting_user_id: str | None = None,
    ) -> SignatureRequest:
        """Подтвердить запрос подписи.

        Person-подписант: обязателен code; user-подписант: acting_user_id должен
        совпадать с signer_user_id.

        КОНТРАКТ ДЛЯ API-СЛОЯ: при PepConflict состояние запроса уже изменено
        (инкремент попыток / expired / declined) — вызывающий обязан COMMIT,
        а не rollback, иначе счётчик попыток теряется (бесконечный перебор кода).
        """
        req = await self._get_own(request_id)
        if req.signer_person_id:
            if req.status != PepStatus.AWAITING_CODE.value:
                raise PepConflict(f"cannot confirm from status {req.status}")
            if not code:
                raise PepConflict("code is required for person signer")
            if req.confirm_code_expires_at is None:
                raise PepConflict("confirmation code state is corrupted (no expiry)")
            expires_at = req.confirm_code_expires_at
            # SQLite returns naive datetimes; normalise to UTC-aware for comparison.
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            outcome = confirm_outcome(
                stored_code_hash=req.confirm_code_hash or "",
                provided_code=code,
                request_id=req.id,
                attempts=req.confirm_attempts,
                expires_at=expires_at,
                now=datetime.now(tz=timezone.utc),
            )
            if outcome is ConfirmOutcome.EXPIRED:
                assert_transition(PepStatus.AWAITING_CODE, PepStatus.EXPIRED)
                req.status = PepStatus.EXPIRED.value
                await self.session.flush()
                raise PepConflict("confirmation code expired")
            if outcome is ConfirmOutcome.EXHAUSTED:
                req.confirm_attempts += 1
                await self._mark_declined(req, reason="attempts_exhausted")
                raise PepConflict("confirmation attempts exhausted")
            if outcome is ConfirmOutcome.WRONG_CODE:
                req.confirm_attempts += 1
                await self.session.flush()
                raise PepConflict("wrong confirmation code")
        else:
            if req.status != PepStatus.CREATED.value:
                raise PepConflict(f"cannot confirm from status {req.status}")
            if acting_user_id is not None and acting_user_id != req.signer_user_id:
                raise PepForbidden("only the designated signer can confirm")
        await self._mark_signed(req)
        return req

    async def decline(self, request_id: str, *, reason: str | None = None) -> SignatureRequest:
        """Отклонить запрос подписи вручную."""
        req = await self._get_own(request_id)
        await self._mark_declined(req, reason=reason or "manual")
        return req

    # --- terminal transitions + events -------------------------------------

    async def _mark_signed(self, req: SignatureRequest) -> None:
        """Перевести запрос в SIGNED, снять код, выслать outbox-событие."""
        try:
            assert_transition(PepStatus(req.status), PepStatus.SIGNED)
        except InvalidTransition as exc:
            raise PepConflict(str(exc)) from exc
        req.status = PepStatus.SIGNED.value
        req.signed_at = datetime.now(tz=timezone.utc)
        req.signer_name = await self._signer_name(
            signer_user_id=req.signer_user_id,
            signer_person_id=req.signer_person_id,
        )
        req.confirm_code_hash = None
        await self._dispatch_signed(req)
        await self._outbox.enqueue(
            tenant_id=self.tenant_id,
            event_type=EventType.PEP_SIGNED.value,
            idempotency_key=f"pep.signed:{req.id}",
            payload={
                "tenant_id": self.tenant_id,
                "signature_request_id": req.id,
                "object_type": req.object_type,
                "object_id": req.object_id,
                "purpose": req.purpose,
                "signer_user_id": req.signer_user_id,
                "signer_person_id": req.signer_person_id,
            },
        )
        await self.session.flush()

    async def _mark_declined(self, req: SignatureRequest, *, reason: str) -> None:
        """Перевести запрос в DECLINED и выслать outbox-событие."""
        try:
            assert_transition(PepStatus(req.status), PepStatus.DECLINED)
        except InvalidTransition as exc:
            raise PepConflict(str(exc)) from exc
        req.status = PepStatus.DECLINED.value
        req.result_json = {**(req.result_json or {}), "declined_reason": reason}
        await self._outbox.enqueue(
            tenant_id=self.tenant_id,
            event_type=EventType.PEP_DECLINED.value,
            idempotency_key=f"pep.declined:{req.id}",
            payload={
                "tenant_id": self.tenant_id,
                "signature_request_id": req.id,
                "reason": reason,
            },
        )
        await self.session.flush()

    # --- hooks (Task 5) ----------------------------------------------------

    async def _approval_gate(self, object_type: str, object_id: str, purpose: str) -> None:
        """Гейт: документ нельзя подписывать, пока активный маршрут не APPROVED.

        Ищем инстансы по обоим якорям (entity_id = id версии ИЛИ id
        документа) — в репо встречаются оба способа привязки.
        Soft-deleted инстансы (deleted_at IS NOT NULL) пропускаются.
        Ознакомления гейт не блокирует.
        """
        if purpose != "document" or object_type != "document_version":
            return None
        doc = await self.session.get(DocumentVersion, object_id)
        anchor_ids = [object_id] + ([doc.document_id] if doc is not None else [])
        rows = (
            (
                await self.session.execute(
                    select(ApprovalInstance)
                    .where(
                        ApprovalInstance.tenant_id == self.tenant_id,
                        ApprovalInstance.entity_id.in_(anchor_ids),
                        ApprovalInstance.deleted_at.is_(None),
                    )
                    .order_by(ApprovalInstance.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        latest = rows[0] if rows else None
        if latest is not None and latest.status != ApprovalInstanceStatus.APPROVED:
            raise PepApprovalRequired("approval_required: document is not approved yet")

    async def _dispatch_signed(self, req: SignatureRequest) -> None:
        """Диспетчер потребителей: проекции на signed по purpose.

        DocumentVersion.signature_status обновляется через core UPDATE, а не через
        ORM-атрибут, чтобы обойти before_update-гард иммутабельности (см.
        DocumentVersionUpdateError в services/documents.py). После UPDATE объект
        вытесняется из identity map, чтобы тест мог прочитать актуальное значение.
        """
        if req.purpose == "document" and req.object_type == "document_version":
            doc = await self.session.get(DocumentVersion, req.object_id)
            if doc is not None and str(doc.tenant_id) == str(self.tenant_id):
                # Core UPDATE — не бьёт ORM before_update event listener.
                # "evaluate" синхронизирует in-memory объект напрямую (Python-
                # оценка WHERE), не через дополнительный SELECT и не через flush.
                await self.session.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.id == req.object_id)
                    .values(signature_status="signed")
                    .execution_options(synchronize_session="evaluate")
                )
        elif req.purpose == "ppe_issue" and req.object_type == "ppe_issue":
            issue = await self.session.get(PPEIssue, req.object_id)
            if issue is not None and str(issue.tenant_id) == str(self.tenant_id):
                issue.signature_doc_ref = f"pep:{req.id}"
        # acknowledgement / briefing: сама запись и есть результат

    async def verify(self, request_id: str) -> dict[str, Any]:
        """Пересчёт канонического hash по ТЕКУЩЕМУ объекту; протокол — в запись."""
        req = await self._get_own(request_id)
        if req.status != PepStatus.SIGNED.value:
            raise PepConflict(f"only signed requests are verifiable, got {req.status}")
        content = await self._build_content(req.object_type, req.object_id)
        actual = content_hash(canonical_payload(req.object_type, req.object_id, content))
        protocol = {
            "checked_at": datetime.now(tz=timezone.utc).isoformat(),
            "expected_hash": req.content_hash,
            "actual_hash": actual,
            "match": actual == req.content_hash,
        }
        req.verification_result_json = protocol
        await self.session.flush()
        return protocol

    async def create_attested(
        self,
        *,
        object_type: str,
        object_id: str,
        purpose: str,
        requested_by: str,
        signer_user_id: str | None = None,
        signer_person_id: str | None = None,
    ) -> SignatureRequest:
        """Attested-подпись: оформитель фиксирует подпись в своём присутствии.

        Для briefings (Срез-1): мгновенный signed и для person-подписанта —
        без кода; факт attestation фиксируется в result_json.

        NB: не валидирует purpose/подписанта и не делает dup-check — ответственность
        вызывающего (briefings: existing-check в sign); guard — Срез-2.
        """
        content = await self._build_content(object_type, object_id)
        payload = canonical_payload(object_type, object_id, content)
        req = SignatureRequest(
            tenant_id=self.tenant_id,
            object_type=object_type,
            object_id=object_id,
            provider="internal",
            provider_code="internal",
            signature_type="pep",
            purpose=purpose,
            requested_by=requested_by,
            signer_user_id=signer_user_id,
            signer_person_id=signer_person_id,
            content_hash=content_hash(payload),
            payload_json={"canonical": payload},
            result_json={"attested_by": requested_by},
            status=PepStatus.CREATED.value,
        )
        self.session.add(req)
        await self.session.flush()
        await self._mark_signed(req)
        return req
