from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.models.models import NPABinding
from app.models.notifications import PlanTask, PlanTaskStatus
from app.models.npa import NpaAct, NpaRevision
from app.models.packages import DocumentPack
from app.models.templates import TemplateVersion


def _binding_kind(row: NPABinding) -> str:
    entity_type = row.entity_type
    return str(entity_type.value if hasattr(entity_type, "value") else entity_type)


def _today() -> date:
    # «Сегодня» — по UTC, как везде в продукте (срез-140), а не по часовому
    # поясу процесса.
    return datetime.now(tz=timezone.utc).date()


def _active_revision(revisions: list[NpaRevision], today: date) -> NpaRevision | None:
    """Действующая редакция: первая по свежести, чей срок покрывает ``today``.

    Редакция с датой вступления в будущем ещё не действует — это и есть
    «черновик → публикация» из разд. 19.4: владелец платформы заводит её
    заранее, а арендаторы узнают о ней в день вступления в силу.
    """
    return next(
        (
            r
            for r in revisions
            if (r.effective_from is None or r.effective_from <= today)
            and (r.effective_to is None or r.effective_to >= today)
        ),
        None,
    )


def _is_stale(row: NPABinding, reference: NpaRevision | None) -> bool:
    """Связь не пересмотрена: сверяли не по той редакции, что действует.

    Без действующей редакции пересматривать нечего — связь актуальна.
    """
    return reference is not None and row.reviewed_revision_id != reference.id


@dataclass(slots=True)
class StaleAct:
    """Акт, у которого есть непересмотренные связи арендатора — для Центра внимания."""

    act_id: str
    code: str
    title: str
    revision_code: str
    stale: int
    total: int


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
        active_revision = selected_revision or _active_revision(revisions, _today())
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
                {row.entity_id for row in binding_rows if _binding_kind(row) == "template_version"}
            ),
            "packages": sorted(
                {row.entity_id for row in binding_rows if _binding_kind(row) == "pack"}
            ),
            "documents": sorted(
                {row.entity_id for row in binding_rows if _binding_kind(row) == "document"}
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
        titles = await self.binding_titles(binding_rows)
        # Срез-144 (разд. 19.4): задачи актуализации — только по связям, которые
        # не пересматривали после действующей (или выбранной) редакции. Без
        # редакций у акта считается всё, как раньше: сверять не с чем, а
        # зависимости назвать надо.
        stale_rows = [row for row in binding_rows if _is_stale(row, active_revision)]
        task_rows = stale_rows if active_revision is not None else binding_rows
        task_summary = self._summary_of(task_rows)
        revision_codes = {r.id: r.revision_code for r in revisions}
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
            # Срез-142: связи по одной, с человеческими именами — для витрины
            # («Связанные сущности») и кнопки «Отвязать».
            "binding_items": [
                {
                    "id": row.id,
                    "npa_id": row.npa_id,
                    "entity_type": _binding_kind(row),
                    "entity_id": row.entity_id,
                    "ref": row.ref,
                    "title": titles.get(row.id, row.entity_id),
                    "reviewed_revision_id": row.reviewed_revision_id,
                    "reviewed_revision_code": revision_codes.get(row.reviewed_revision_id or ""),
                    "stale": _is_stale(row, active_revision),
                }
                for row in sorted(binding_rows, key=lambda r: (_binding_kind(r), r.created_at))
            ],
            "summary": summary,
            "stale_bindings": len(stale_rows),
            "tasks_to_create": [
                {
                    "code": f"npa-update-{key}",
                    "title": f"Актуализировать зависимости НПА: {key}",
                    "count": count,
                }
                for key, count in task_summary.items()
                if count > 0
            ],
        }

    @staticmethod
    def _summary_of(rows: list[NPABinding]) -> dict[str, int]:
        """Те же ключи, что у ``summary``, но по произвольному подмножеству связей."""
        from_context = {
            "risks": "risk_id",
            "checklists": "checklist_id",
            "workflows": "workflow_definition_id",
            "roles": "role_code",
            "sites": "site_id",
        }
        counts = {
            "templates": len({r.entity_id for r in rows if _binding_kind(r) == "template_version"}),
            "packages": len({r.entity_id for r in rows if _binding_kind(r) == "pack"}),
            "documents": len({r.entity_id for r in rows if _binding_kind(r) == "document"}),
        }
        for key, context_key in from_context.items():
            counts[key] = len(
                {
                    str((r.context or {}).get(context_key))
                    for r in rows
                    if (r.context or {}).get(context_key)
                }
            )
        return counts

    async def active_revision_for(self, act_id: str) -> NpaRevision | None:
        """Действующая сегодня редакция акта — то, «по чему» сверяют связь."""
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
        return _active_revision(list(revisions), _today())

    async def stale_acts(self) -> list[StaleAct]:
        """Акты с непересмотренными связями арендатора — по одному на акт.

        Это «уведомление» разд. 19.4 в форме, которая не требует писать в чужие
        арендаторские таблицы из-под владельца платформы: арендатор видит факт
        в своём Центре внимания при следующем же запросе.
        """
        binding_rows = (
            (
                await self.session.execute(
                    select(NPABinding).where(NPABinding.tenant_id == self.tenant_id)
                )
            )
            .scalars()
            .all()
        )
        if not binding_rows:
            return []
        by_act: dict[str, list[NPABinding]] = {}
        for row in binding_rows:
            by_act.setdefault(row.npa_id, []).append(row)
        acts = (
            (
                await self.session.execute(
                    select(NpaAct)
                    .options(selectinload(NpaAct.revisions))
                    .where(NpaAct.id.in_(by_act))
                    .order_by(NpaAct.code)
                )
            )
            .scalars()
            .all()
        )
        today = _today()
        result: list[StaleAct] = []
        for act in acts:
            revisions = sorted(
                act.revisions,
                key=lambda r: (r.effective_from or date.min, r.created_at),
                reverse=True,
            )
            active = _active_revision(revisions, today)
            if active is None:
                continue
            rows = by_act[act.id]
            stale = sum(1 for row in rows if _is_stale(row, active))
            if stale:
                result.append(
                    StaleAct(
                        act_id=act.id,
                        code=act.code,
                        title=act.title,
                        revision_code=active.revision_code,
                        stale=stale,
                        total=len(rows),
                    )
                )
        return result

    async def binding_titles(self, rows: list[NPABinding]) -> dict[str, str]:
        """Имена целей связей: документ — «шаблон · организация», версия шаблона —
        «шаблон v3», пакет — его имя. Цель, которой уже нет, подписана её id."""
        by_kind: dict[str, set[str]] = {}
        for row in rows:
            by_kind.setdefault(_binding_kind(row), set()).add(row.entity_id)
        names: dict[tuple[str, str], str] = {}
        if by_kind.get("document"):
            documents = (
                await self.session.execute(
                    select(Document)
                    .options(selectinload(Document.template), selectinload(Document.company))
                    .where(
                        Document.tenant_id == self.tenant_id,
                        Document.id.in_(by_kind["document"]),
                    )
                )
            ).scalars()
            for document in documents:
                # Та же формула, что у списка документов (_build_document_ui_read).
                name = (
                    document.template.name if document.template else None
                ) or f"Document {document.id[:8]}"
                company = document.company.name if document.company else None
                names[("document", document.id)] = f"{name} · {company}" if company else name
        if by_kind.get("template_version"):
            versions = (
                await self.session.execute(
                    select(TemplateVersion)
                    .options(selectinload(TemplateVersion.template))
                    .where(
                        TemplateVersion.tenant_id == self.tenant_id,
                        TemplateVersion.id.in_(by_kind["template_version"]),
                    )
                )
            ).scalars()
            for version in versions:
                template_name = version.template.name if version.template else "Шаблон"
                names[("template_version", version.id)] = f"{template_name} v{version.version}"
        if by_kind.get("pack"):
            packs = (
                await self.session.execute(
                    select(DocumentPack).where(
                        DocumentPack.tenant_id == self.tenant_id,
                        DocumentPack.id.in_(by_kind["pack"]),
                    )
                )
            ).scalars()
            for pack in packs:
                names[("pack", pack.id)] = pack.name
        return {
            row.id: names.get((_binding_kind(row), row.entity_id), row.entity_id) for row in rows
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
