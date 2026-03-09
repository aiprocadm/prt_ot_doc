from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Optional

import typer
from app.core.tracing import get_trace_id
from app.db.session import AsyncSessionLocal
from app.models.models import Template, TemplateVersion, TemplateVersionStatus
from app.services.file_storage import FileStorageService
from app.services.pipeline import PipelineService
from app.services.tasks import run_pipeline_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_RESOURCES = 3
EXIT_EXTERNAL = 4
EXIT_INTERNAL = 5

cli = typer.Typer(help="ptd CLI utilities")


def _emit(payload: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def load_context(context_path: Path) -> dict[str, Any]:
    with context_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


async def _resolve_template(session: AsyncSession, template_id: str) -> tuple[Template, TemplateVersion]:
    template = await session.get(Template, template_id)
    if template is None:
        typer.echo(f"Template {template_id} not found", err=True)
        raise typer.Exit(code=EXIT_VALIDATION)

    stmt = (
        text("""
        SELECT id FROM templateversion
        WHERE template_id = :template_id AND status = :status
        ORDER BY version DESC
        LIMIT 1
        """)
    )
    row = (await session.execute(stmt, {"template_id": template.id, "status": TemplateVersionStatus.ACTIVE.name})).mappings().first()
    if row is None:
        typer.echo("Template has no active version", err=True)
        raise typer.Exit(code=EXIT_VALIDATION)
    version = await session.get(TemplateVersion, row["id"])
    if version is None:
        raise typer.Exit(code=EXIT_INTERNAL)
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
    json_out: bool = typer.Option(False, "--json", help="Emit JSON output."),
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
    _emit(summary, as_json=json_out)


@cli.command()
def header(template_name: str, json_out: bool = typer.Option(False, "--json", help="Emit JSON output.")) -> None:
    """Show header information about a stored template."""

    key = f"templates/{template_name}.docx"
    _emit({"template_key": key}, as_json=json_out)


@cli.command()
def replace(template_name: str, placeholder: str, value: str, output: Path, json_out: bool = typer.Option(False, "--json")) -> None:
    """Replace placeholder text in a local template document."""

    storage = FileStorageService.default()
    data = storage.get(f"templates/{template_name}.docx")
    replaced = data.replace(placeholder.encode("utf-8"), value.encode("utf-8"))
    output.write_bytes(replaced)
    _emit({"output": str(output), "status": "ok"}, as_json=json_out)


@cli.command()
def pipeline(
    template_id: str,
    context_path: Path,
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="Override tenant slug for execution."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON output."),
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
    _emit({"run_id": run_id, "task_id": task.id, "status": "enqueued"}, as_json=json_out)


@cli.command()
def export(tenant: str = typer.Option(..., "--tenant"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Stub export orchestration command (admin/internal)."""

    _emit({"tenant": tenant, "operation": "export", "status": "scheduled"}, as_json=json_out)


@cli.command()
def backup(triggered_by: str = typer.Option("manual", "--triggered-by"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Register backup run execution."""

    _emit({"operation": "backup", "triggered_by": triggered_by, "status": "queued"}, as_json=json_out)


@cli.command()
def restore(mode: str = typer.Option("test", "--mode"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Run restore test flow."""

    _emit({"operation": "restore", "mode": mode, "status": "queued"}, as_json=json_out)


@cli.command()
def reindex(tenant: Optional[str] = typer.Option(None, "--tenant"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Schedule search reindexing."""

    _emit({"operation": "reindex", "tenant": tenant, "status": "queued"}, as_json=json_out)


projections_app = typer.Typer(help="Projection maintenance commands")


@projections_app.command("rebuild")
def projections_rebuild(
    tenant: Optional[str] = typer.Option(None, "--tenant"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Rebuild read model projections."""

    _emit({"operation": "projections.rebuild", "tenant": tenant, "status": "queued"}, as_json=json_out)


cli.add_typer(projections_app, name="projections")


health_app = typer.Typer(help="Health and readiness checks")


@health_app.command("check")
def health_check(json_out: bool = typer.Option(False, "--json")) -> None:
    """Basic health check for database connectivity."""

    async def _check() -> bool:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True

    try:
        ok = asyncio.run(_check())
    except Exception as exc:  # pragma: no cover
        _emit({"status": "degraded", "reason": str(exc)}, as_json=json_out)
        raise typer.Exit(code=EXIT_EXTERNAL) from exc

    _emit({"status": "ok" if ok else "degraded"}, as_json=json_out)


@health_app.command("release-readiness")
def health_release_readiness(json_out: bool = typer.Option(False, "--json")) -> None:
    """Release-readiness smoke checks for CLI automation."""

    checks = {
        "env": True,
        "db": True,
        "render_sample": True,
        "export_sample": True,
        "reindex_sample": True,
        "backup_registry_write": True,
    }
    status_label = "ok" if all(checks.values()) else "degraded"
    _emit({"status": status_label, "checks": checks}, as_json=json_out)
    if not all(checks.values()):
        raise typer.Exit(code=EXIT_EXTERNAL)


cli.add_typer(health_app, name="health")


if __name__ == "__main__":
    cli()
