from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NPABinding
from app.models.notifications import PlanTask, PlanTaskStatus
from app.models.npa import NpaAct, NpaRevision


@dataclass(slots=True)
class NpaImpactService:
    session: AsyncSession
    tenant_id: str

    async def detail(self, act_id: str, revision_id: str | None = None) -> dict[str, Any] | None:
        act = await self.session.get(NpaAct, act_id)
        if act is None:
            return None
        revisions = (
            (
                await self.session.execute(
                    select(NpaRevision)
                    .where(NpaRevision.act_id == act_id)
                    .order_by(
                        NpaRevision.effective_from.desc().nullslast(), NpaRevision.created_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        selected_revision = (
            next((r for r in revisions if r.id == revision_id), None) if revision_id else None
        )
        active_revision = selected_revision or next(
            (
                r
                for r in revisions
                if (r.effective_from is None or r.effective_from <= date.today())
                and (r.effective_to is None or r.effective_to >= date.today())
            ),
            None,
        )
        binding_rows = (
            (
                await self.session.execute(
                    select(NPABinding).where(
                        NPABinding.tenant_id == self.tenant_id, NPABinding.npa_id == act_id
                    )
                )
            )
            .scalars()
            .all()
        )
        linked = {
            "templates": sorted(
                {
                    row.entity_id
                    for row in binding_rows
                    if str(
                        row.entity_type.value
                        if hasattr(row.entity_type, "value")
                        else row.entity_type
                    )
                    == "template_version"
                }
            ),
            "packages": sorted(
                {
                    row.entity_id
                    for row in binding_rows
                    if str(
                        row.entity_type.value
                        if hasattr(row.entity_type, "value")
                        else row.entity_type
                    )
                    == "pack"
                }
            ),
            "documents": sorted(
                {
                    row.entity_id
                    for row in binding_rows
                    if str(
                        row.entity_type.value
                        if hasattr(row.entity_type, "value")
                        else row.entity_type
                    )
                    == "document"
                }
            ),
            "risks": sorted(
                {
                    str((row.context or {}).get("risk_id"))
                    for row in binding_rows
                    if (row.context or {}).get("risk_id")
                }
            ),
            "checklists": sorted(
                {
                    str((row.context or {}).get("checklist_id"))
                    for row in binding_rows
                    if (row.context or {}).get("checklist_id")
                }
            ),
            "workflows": sorted(
                {
                    str((row.context or {}).get("workflow_definition_id"))
                    for row in binding_rows
                    if (row.context or {}).get("workflow_definition_id")
                }
            ),
            "roles": sorted(
                {
                    str((row.context or {}).get("role_code"))
                    for row in binding_rows
                    if (row.context or {}).get("role_code")
                }
            ),
            "sites": sorted(
                {
                    str((row.context or {}).get("site_id"))
                    for row in binding_rows
                    if (row.context or {}).get("site_id")
                }
            ),
        }
        summary = {key: len(value) for key, value in linked.items()}
        return {
            "act": {
                "id": act.id,
                "code": act.code,
                "title": act.title,
                "edition": act.edition,
                "valid_from": act.valid_from.isoformat() if act.valid_from else None,
                "valid_to": act.valid_to.isoformat() if act.valid_to else None,
            },
            "revisions": [
                {
                    "id": r.id,
                    "revision_code": r.revision_code,
                    "title": r.title,
                    "effective_from": r.effective_from.isoformat() if r.effective_from else None,
                    "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                    "change_summary": r.change_summary,
                }
                for r in revisions
            ],
            "active_revision_id": active_revision.id if active_revision else None,
            "selected_revision_id": selected_revision.id if selected_revision else None,
            "bindings": linked,
            "summary": summary,
            "tasks_to_create": [
                {
                    "code": f"npa-update-{key}",
                    "title": f"Актуализировать зависимости НПА: {key}",
                    "count": count,
                }
                for key, count in summary.items()
                if count > 0
            ],
        }

    async def create_update_tasks(
        self, act_id: str, created_by: str | None, revision_id: str | None = None
    ) -> list[PlanTask]:
        payload = await self.detail(act_id, revision_id=revision_id)
        if payload is None:
            return []
        tasks: list[PlanTask] = []
        for item in payload["tasks_to_create"]:
            existing = (
                await self.session.execute(
                    select(PlanTask).where(
                        PlanTask.tenant_id == self.tenant_id,
                        PlanTask.entity_type == "npa",
                        PlanTask.entity_id == act_id,
                        PlanTask.title == item["title"],
                        PlanTask.status == PlanTaskStatus.OPEN,
                        PlanTask.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                tasks.append(existing)
                continue
            task = PlanTask(
                tenant_id=self.tenant_id,
                title=item["title"],
                description=f"NPA impact analysis for act {payload['act']['code']}"
                + (
                    f" revision {payload['selected_revision_id']}"
                    if payload.get("selected_revision_id")
                    else ""
                ),
                entity_type="npa",
                entity_id=act_id,
                assignee_id=created_by,
                status=PlanTaskStatus.OPEN,
            )
            self.session.add(task)
            tasks.append(task)
        await self.session.flush()
        return tasks
