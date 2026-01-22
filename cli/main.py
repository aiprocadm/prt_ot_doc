from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Optional

import typer
from sqlalchemy import select

from app.core.tracing import get_trace_id
from app.db.session import AsyncSessionLocal
from app.models.models import Template, TemplateVersion, TemplateVersionStatus
from app.services.file_storage import FileStorageService
from app.services.pipeline import PipelineService
from app.services.tasks import run_pipeline_task

cli = typer.Typer(help="ptd CLI utilities")


def load_context(context_path: Path) -> dict[str, Any]:
    with context_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


async def _resolve_template(session, template_id: str) -> tuple[Template, TemplateVersion]:
    template = await session.get(Template, template_id)
    if template is None:
        typer.echo(f"Template {template_id} not found", err=True)
        raise typer.Exit(code=1)

    stmt = (
        select(TemplateVersion)
        .where(
            TemplateVersion.template_id == template.id,
            TemplateVersion.status == TemplateVersionStatus.ACTIVE,
        )
        .order_by(TemplateVersion.version.desc())
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        typer.echo("Template has no active version", err=True)
        raise typer.Exit(code=1)
    return template, version


def _extract_payload(
    data: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str] | None, str | None, str | None, str | None]:
    context = data.get("context") if isinstance(data.get("context"), dict) else data
    replacements = data.get("replacements")
    header_text = data.get("header_text")
    footer_text = data.get("footer_text")
    output_basename = data.get("output_basename")
    return context, replacements, header_text, footer_text, output_basename


@cli.command()
def render(
    template_id: str,
    context_path: Path,
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="Override tenant slug for execution."
    ),
) -> None:
    """Render a template synchronously using the pipeline service."""

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal(tenant=tenant) as session:
            payload = load_context(context_path)
            (
                context,
                replacements,
                header_text,
                footer_text,
                output_basename,
            ) = _extract_payload(payload)
            template, version = await _resolve_template(session, template_id)
            service = PipelineService()
            run = await service.run(
                session=session,
                template=template,
                template_version=version,
                context=context,
                replacements=replacements,
                header_text=header_text,
                footer_text=footer_text,
                idempotency_key=payload.get("idempotency_key") or str(uuid.uuid4()),
                output_basename=output_basename,
                tenant_id=tenant or template.tenant_id,
            )
            return {
                "id": run.id,
                "status": run.status.value,
                "outputs": run.outputs or {},
                "result_metadata": run.result_metadata,
            }

    summary = asyncio.run(_run())
    typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))


@cli.command()
def header(template_name: str) -> None:
    """Show header information about a stored template."""

    key = f"templates/{template_name}.docx"
    typer.echo(f"Template key: {key}")


@cli.command()
def replace(template_name: str, placeholder: str, value: str, output: Path) -> None:
    """Replace placeholder text in a local template document."""

    storage = FileStorageService.default()
    data = storage.get(f"templates/{template_name}.docx")
    replaced = data.replace(placeholder.encode("utf-8"), value.encode("utf-8"))
    output.write_bytes(replaced)
    typer.echo(f"Written updated template to {output}")


@cli.command()
def pipeline(
    template_id: str,
    context_path: Path,
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="Override tenant slug for execution."
    ),
) -> None:
    """Enqueue a pipeline execution via Celery."""

    payload = load_context(context_path)
    (
        context,
        replacements,
        header_text,
        footer_text,
        output_basename,
    ) = _extract_payload(payload)
    idempotency_key = payload.get("idempotency_key") or str(uuid.uuid4())

    async def _enqueue() -> tuple[str, str]:
        async with AsyncSessionLocal(tenant=tenant) as session:
            template, version = await _resolve_template(session, template_id)
            service = PipelineService()
            run, _ = await service.ensure_pending_run(
                session,
                template=template,
                template_version=version,
                context=context,
                replacements=replacements,
                header_text=header_text,
                footer_text=footer_text,
                idempotency_key=idempotency_key,
                output_basename=output_basename,
                tenant_id=tenant or template.tenant_id,
            )
            await session.commit()
            await session.refresh(run)
            return run.id, run.tenant_id

    run_id, tenant_slug = asyncio.run(_enqueue())
    trace_id = get_trace_id(default=str(uuid.uuid4()))
    task = run_pipeline_task.apply_async(
        args=[run_id, tenant_slug],
        task_id=run_id,
        headers={"trace_id": trace_id},
    )
    typer.echo(f"Enqueued pipeline run {run_id} as task {task.id}")


if __name__ == "__main__":
    cli()
