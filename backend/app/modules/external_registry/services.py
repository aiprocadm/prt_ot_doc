from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ExternalRegistryJob, TrainingCertificate, TrainingProtocol


@dataclass
class RegistryResponse:
    status: str
    payload: dict


class FRDOAdapter:
    async def send(self, payload: dict) -> RegistryResponse:
        accepted = int(payload.get("entity_id", "0")[-1], 16) % 2 == 0
        return RegistryResponse(status="accepted" if accepted else "rejected", payload={"provider": "frdo", "accepted": accepted})


class EISOTAdapter:
    async def send(self, payload: dict) -> RegistryResponse:
        accepted = int(payload.get("entity_id", "0")[-1], 16) % 2 == 1
        return RegistryResponse(status="accepted" if accepted else "rejected", payload={"provider": "eisot", "accepted": accepted})


class ExternalRegistryDispatchService:
    async def enqueue(self, session: AsyncSession, tenant_id: str, entity_type: str, entity_id: str, registry_type: str) -> ExternalRegistryJob:
        job = ExternalRegistryJob(tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id, registry_type=registry_type, status="pending")
        session.add(job)
        await session.flush()
        return job

    async def dispatch(self, session: AsyncSession, job: ExternalRegistryJob) -> ExternalRegistryJob:
        adapter = FRDOAdapter() if job.registry_type == "frdo" else EISOTAdapter()
        request_payload = {"entity_type": job.entity_type, "entity_id": job.entity_id}
        response = await adapter.send(request_payload)
        job.request_payload = request_payload
        job.response_payload = response.payload
        job.status = response.status

        job_tid = str(job.tenant_id)
        if job.entity_type == "certificate":
            cert = await session.get(TrainingCertificate, job.entity_id)
            if cert is not None and str(cert.tenant_id) == job_tid:
                cert.external_registry_payload = response.payload
                cert.external_registry_status = response.status
        if job.entity_type == "protocol":
            protocol = await session.get(TrainingProtocol, job.entity_id)
            if protocol is not None and str(protocol.tenant_id) == job_tid:
                protocol.status = "issued" if response.status == "accepted" else protocol.status
        await session.flush()
        return job
