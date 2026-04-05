from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class MockSignatureProvider:
    async def create_signature_request(self, request: SignatureRequest) -> dict:
        return {"external_request_id": f"mock-{request.id}", "status": "pending"}

    async def cancel_signature_request(self, request: SignatureRequest) -> dict:
        return {"status": "canceled"}

    async def get_signature_status(self, request: SignatureRequest) -> dict:
        return {"status": "signed", "certificate_thumbprint": "MOCK-THUMBPRINT", "signer_name": "Mock Signer"}

    async def verify_signature(self, request: SignatureRequest) -> dict:
        return {"verified": True, "certificate": {"subject": "Mock Signer"}}


class SignatureRequestService:
    def __init__(self, session: AsyncSession, tenant_id: str, provider: SignatureProvider | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.provider = provider or MockSignatureProvider()

    async def create(self, request: SignatureRequest) -> SignatureRequest:
        if request.approval_instance_id:
            approval = await self.session.get(ApprovalInstance, request.approval_instance_id)
            if (
                not approval
                or str(approval.tenant_id) != str(self.tenant_id)
                or approval.status != ApprovalInstanceStatus.APPROVED
            ):
                raise HTTPException(status.HTTP_409_CONFLICT, "Approval instance must be approved")
        meta = await self.provider.create_signature_request(request)
        request.external_request_id = meta.get("external_request_id")
        request.status = meta.get("status", "pending")
        self.session.add(request)
        await self.session.flush()
        return request


class SignatureVerificationService:
    def __init__(self, session: AsyncSession, tenant_id: str, provider: SignatureProvider | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.provider = provider or MockSignatureProvider()

    async def refresh(self, request: SignatureRequest) -> SignatureRequest:
        data = await self.provider.get_signature_status(request)
        request.status = data.get("status", request.status)
        request.certificate_thumbprint = data.get("certificate_thumbprint")
        request.signer_name = data.get("signer_name")
        if request.status == "signed":
            request.signed_at = datetime.now(tz=timezone.utc)
        await self.session.flush()
        return request

    async def verify(self, request: SignatureRequest) -> SignatureRequest:
        request.status = "verifying"
        await self.session.flush()
        result = await self.provider.verify_signature(request)
        request.verification_result_json = result
        request.status = "verified" if result.get("verified") else "failed"
        await self.session.flush()
        return request
