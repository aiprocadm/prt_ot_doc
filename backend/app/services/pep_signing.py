"""PEP signing service (vNext §6.9): session-aware оркестрация чистого домена.

Создание/подтверждение/отклонение запросов ПЭП, построение канонического
payload по типу объекта, гейт согласования (Task 5), диспетчер потребителей
на signed (Task 5), outbox-события.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
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
from app.models.document import DocumentVersion
from app.models.models import BriefingEntry, Person, PPEIssue, SignatureRequest
from app.services.events import EventType
from app.services.outbox import OutboxService


class PepNotFound(LookupError):
    """Объект/запрос не найден (или чужой тенант)."""


class PepConflict(ValueError):
    """Бизнес-конфликт: дубль, неверный/истёкший код, недопустимый переход."""


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
            outcome = confirm_outcome(
                stored_code_hash=req.confirm_code_hash or "",
                provided_code=code,
                request_id=req.id,
                attempts=req.confirm_attempts,
                expires_at=req.confirm_code_expires_at,
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
                raise PepConflict("only the designated signer can confirm")
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

    # --- hooks, реализуются в Task 5 ---------------------------------------

    async def _approval_gate(self, object_type: str, object_id: str, purpose: str) -> None:
        """Гейт согласования перед созданием запроса — реализуется в Task 5."""
        return None

    async def _dispatch_signed(self, req: SignatureRequest) -> None:
        """Диспетчер постобработки после подписания — реализуется в Task 5."""
        return None
