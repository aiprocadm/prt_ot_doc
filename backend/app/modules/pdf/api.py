from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
from app.models.file import File
from app.modules.pdf.models import PdfConversionRun, PdfRunStatus
from app.modules.pdf.schemas import ConvertPdfAccepted, ConvertPdfRequest, PdfRunRead
from app.services.idempotency import IdempotencyService, normalize_idempotency_key

router = APIRouter()


@router.post("/{file_id}/convert:pdf", response_model=ConvertPdfAccepted, status_code=status.HTTP_202_ACCEPTED)
async def convert_file_to_pdf(
    file_id: str,
    payload: ConvertPdfRequest,
    request: Request,
    response: Response,
    tenant=Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ConvertPdfAccepted:
    if payload.mode != "docx_to_pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unsupported_mode")
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="idempotency_key_required")

    normalized_key = normalize_idempotency_key(idempotency_key)
    request_hash = compute_request_hash({"file_id": file_id, "payload": payload.model_dump(mode="json")})
    idem = IdempotencyService(session, tenant_id=str(tenant.id), route_key="files.convert_pdf")
    record, created = await idem.acquire(key=normalized_key, request_hash=request_hash)
    if not created:
        return await idem.respond_from_store(record, model=ConvertPdfAccepted, response=response)

    file_row = await session.get(File, file_id)
    if file_row is None or file_row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file_not_found")

    run = PdfConversionRun(
        tenant_id=str(tenant.id),
        input_file_id=file_row.id,
        status=PdfRunStatus.QUEUED.value,
        timeout_s=payload.options.timeout_s,
        attempts=0,
        correlation_id=request.headers.get("X-Request-Id") or str(uuid4()),
    )
    session.add(run)
    await session.flush()

    from app.celery.tasks.convert_pdf_job import convert_pdf_job

    task = convert_pdf_job.delay(
        tenant_id=str(tenant.id),
        input_file_id=file_row.id,
        pdf_run_id=run.id,
        options=payload.options.model_dump(mode="json"),
        correlation_id=run.correlation_id,
    )

    body = ConvertPdfAccepted(
        job_id=task.id,
        pdf_run_id=run.id,
        output_file_id=None,
        status_url=f"/api/v1/files/pdf-runs/{run.id}",
    )
    await idem.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=body.model_dump(mode="json"))
    await session.commit()
    return body


@router.get("/pdf-runs/{pdf_run_id}", response_model=PdfRunRead)
async def get_pdf_run(
    pdf_run_id: str,
    tenant=Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
) -> PdfRunRead:
    run = await session.get(PdfConversionRun, pdf_run_id)
    if run is None or run.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pdf_run_not_found")
    return PdfRunRead.model_validate(run, from_attributes=True)
