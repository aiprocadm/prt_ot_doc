from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ApprovalInstance, ApprovalInstanceStatus, SignatureRequest


class SignatureProvider(Protocol):
    async def create_signature_request(self, request: SignatureRequest) -> dict: ...
    async def cancel_signature_request(self, request: SignatureRequest) -> dict: ...
    async def get_signature_status(self, request: SignatureRequest) -> dict: ...
    async def verify_signature(self, request: SignatureRequest) -> dict: ...


# Мок-провайдер удалён (Срез-1 чистка симуляции).
# Реальные провайдеры KEP/UNEP появятся при продуктовой интеграции.
# ПЭП-подписание живёт в services/pep_signing.py.


class SignatureRequestService:
    """Сервис создания запросов подписи через внешнего провайдера.

    provider=None означает «провайдер не сконфигурирован» — запросы
    отклоняются с 409 до момента реальной интеграции.
    """

    def __init__(
        self, session: AsyncSession, tenant_id: str, provider: SignatureProvider | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.provider = provider

    async def create(self, request: SignatureRequest) -> SignatureRequest:
        if request.approval_instance_id:
            approval = await self.session.get(ApprovalInstance, request.approval_instance_id)
            if (
                not approval
                or str(approval.tenant_id) != str(self.tenant_id)
                or approval.status != ApprovalInstanceStatus.APPROVED
            ):
                raise HTTPException(status.HTTP_409_CONFLICT, "Approval instance must be approved")
        if self.provider is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "signature provider is not configured")
        meta = await self.provider.create_signature_request(request)
        request.external_request_id = meta.get("external_request_id")
        request.status = meta.get("status", "pending")
        self.session.add(request)
        await self.session.flush()
        return request


class SignatureVerificationService:
    """Сервис проверки/обновления статуса подписи через внешнего провайдера.

    provider=None означает «провайдер не сконфигурирован» — отклоняется с 409.
    """

    def __init__(
        self, session: AsyncSession, tenant_id: str, provider: SignatureProvider | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.provider = provider

    async def refresh(self, request: SignatureRequest) -> SignatureRequest:
        if self.provider is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "signature provider is not configured")
        data = await self.provider.get_signature_status(request)
        request.status = data.get("status", request.status)
        request.certificate_thumbprint = data.get("certificate_thumbprint")
        request.signer_name = data.get("signer_name")
        if request.status == "signed":
            request.signed_at = datetime.now(tz=timezone.utc)
        await self.session.flush()
        return request

    async def verify(self, request: SignatureRequest) -> SignatureRequest:
        if self.provider is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "signature provider is not configured")
        request.status = "verifying"
        await self.session.flush()
        result = await self.provider.verify_signature(request)
        request.verification_result_json = result
        request.status = "verified" if result.get("verified") else "failed"
        await self.session.flush()
        return request
