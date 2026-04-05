from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.models import (
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceStatus,
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTimelineEvent,
)
from app.services.audit import AuditService
from app.services.outbox import OutboxService

ALLOWED_NODE_TYPES = {"start", "task", "approval", "condition", "timer", "notification", "webhook", "integration_call", "end"}


@dataclass(slots=True)
class DefinitionGraph:
    nodes: list[dict[str, Any]]
    transitions: list[dict[str, Any]]


class WorkflowService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.audit = AuditService(session)
        self.outbox = OutboxService(session)

    async def create_definition(self, *, code: str, name: str, description: str | None, entity_type: str, graph: dict[str, Any], variables_schema: dict[str, Any], actor_user_id: str | None) -> WorkflowDefinitionVersion:
        self.validate_graph(graph)
        existing = (await self.session.execute(select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == self.tenant_id, WorkflowDefinition.code == code, WorkflowDefinition.deleted_at.is_(None)))).scalar_one_or_none()
        if existing is None:
            definition = WorkflowDefinition(tenant_id=self.tenant_id, code=code, name=name, description=description, entity_type=entity_type)
            self.session.add(definition)
            await self.session.flush()
        else:
            definition = existing
            definition.name = name
            definition.description = description
            definition.entity_type = entity_type
        current_max = await self.session.scalar(select(WorkflowDefinitionVersion.version_no).where(WorkflowDefinitionVersion.tenant_id == self.tenant_id, WorkflowDefinitionVersion.definition_id == definition.id).order_by(WorkflowDefinitionVersion.version_no.desc()).limit(1))
        version = WorkflowDefinitionVersion(
            tenant_id=self.tenant_id,
            definition_id=definition.id,
            version_no=int(current_max or 0) + 1,
            status=WorkflowDefinitionStatus.DRAFT,
            graph_json=graph,
            variables_schema=variables_schema,
        )
        self.session.add(version)
        await self.session.flush()
        await self._timeline_like_audit("workflow.definition.create", actor_user_id, definition.id, {"code": code, "version_no": version.version_no})
        return version

    def validate_graph(self, graph: dict[str, Any]) -> None:
        nodes = graph.get("nodes") or []
        transitions = graph.get("transitions") or []
        if not nodes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow graph requires nodes")
        node_ids = set()
        start_count = 0
        end_count = 0
        start_node_id: str | None = None
        for node in nodes:
            node_id = node.get("id")
            node_type = node.get("type")
            if not node_id or node_id in node_ids:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow node ids must be unique")
            if node_type not in ALLOWED_NODE_TYPES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unsupported workflow node type: {node_type}")
            if node_type == "start":
                start_count += 1
                start_node_id = str(node_id)
            if node_type == "end":
                end_count += 1
            node_ids.add(node_id)
        if start_count != 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow graph requires exactly one start node")
        if end_count < 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow graph requires at least one end node")
        for transition in transitions:
            if transition.get("from") not in node_ids or transition.get("to") not in node_ids:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow transition references unknown node")
        if not any(transition.get("from") == start_node_id for transition in transitions):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow start node must have at least one outgoing transition")
        adjacency: dict[str, list[str]] = {str(node_id): [] for node_id in node_ids}
        for transition in transitions:
            adjacency[str(transition["from"])].append(str(transition["to"]))
        visited: set[str] = set()
        queue = [start_node_id] if start_node_id else []
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            queue.extend(adjacency.get(current, []))
        unreachable = node_ids - visited
        if unreachable:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"workflow graph contains unreachable nodes: {', '.join(sorted(unreachable))}")
        terminal_nodes = {str(node.get("id")) for node in nodes if node.get("type") == "end"}
        if not any(end_node in visited for end_node in terminal_nodes):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow graph must reach an end node")

    async def publish_version(self, version_id: str, actor_user_id: str | None) -> WorkflowDefinitionVersion:
        version = await self.session.get(WorkflowDefinitionVersion, version_id)
        if version is None or version.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow version not found")
        definition = await self.session.get(WorkflowDefinition, version.definition_id)
        if definition is None or definition.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow definition not found")
        existing_versions = (await self.session.execute(select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.tenant_id == self.tenant_id, WorkflowDefinitionVersion.definition_id == definition.id, WorkflowDefinitionVersion.id != version.id, WorkflowDefinitionVersion.status == WorkflowDefinitionStatus.PUBLISHED))).scalars().all()
        for item in existing_versions:
            item.status = WorkflowDefinitionStatus.ARCHIVED
            item.archived_at = datetime.now(tz=timezone.utc)
        version.status = WorkflowDefinitionStatus.PUBLISHED
        version.published_at = datetime.now(tz=timezone.utc)
        definition.current_version_id = version.id
        await self.session.flush()
        await self._timeline_like_audit("workflow.definition.publish", actor_user_id, definition.id, {"version_no": version.version_no})
        return version

    async def archive_version(self, version_id: str, actor_user_id: str | None) -> WorkflowDefinitionVersion:
        version = await self.session.get(WorkflowDefinitionVersion, version_id)
        if version is None or version.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow version not found")
        version.status = WorkflowDefinitionStatus.ARCHIVED
        version.archived_at = datetime.now(tz=timezone.utc)
        await self.session.flush()
        await self._timeline_like_audit("workflow.definition.archive", actor_user_id, version.definition_id, {"version_no": version.version_no})
        return version

    async def list_definitions(self) -> list[WorkflowDefinition]:
        rows = (await self.session.execute(select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == self.tenant_id, WorkflowDefinition.deleted_at.is_(None)).order_by(WorkflowDefinition.updated_at.desc()))).scalars().all()
        return rows

    async def list_instances(self, *, status_filter: WorkflowInstanceStatus | None = None, entity_type: str | None = None) -> list[tuple[WorkflowInstance, int]]:
        stmt = (
            select(WorkflowInstance, func.count(WorkflowTask.id))
            .outerjoin(
                WorkflowTask,
                and_(
                    WorkflowTask.instance_id == WorkflowInstance.id,
                    WorkflowTask.tenant_id == self.tenant_id,
                    WorkflowTask.deleted_at.is_(None),
                    WorkflowTask.status == WorkflowTaskStatus.OPEN,
                ),
            )
            .where(WorkflowInstance.tenant_id == self.tenant_id, WorkflowInstance.deleted_at.is_(None))
            .group_by(WorkflowInstance.id)
            .order_by(WorkflowInstance.updated_at.desc())
        )
        if status_filter is not None:
            stmt = stmt.where(WorkflowInstance.status == status_filter)
        if entity_type:
            stmt = stmt.where(WorkflowInstance.entity_type == entity_type)
        return list((await self.session.execute(stmt)).all())

    async def get_versions(self, definition_id: str) -> list[WorkflowDefinitionVersion]:
        rows = (await self.session.execute(select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.tenant_id == self.tenant_id, WorkflowDefinitionVersion.definition_id == definition_id, WorkflowDefinitionVersion.deleted_at.is_(None)).order_by(WorkflowDefinitionVersion.version_no.desc()))).scalars().all()
        return rows

    async def start_instance(self, *, definition_code: str | None, version_id: str | None, entity_type: str, entity_id: str, context: dict[str, Any], actor_user_id: str | None, correlation_id: str | None) -> WorkflowInstance:
        version = None
        if version_id:
            version = await self.session.get(WorkflowDefinitionVersion, version_id)
        elif definition_code:
            definition = (await self.session.execute(select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == self.tenant_id, WorkflowDefinition.code == definition_code, WorkflowDefinition.deleted_at.is_(None)))).scalar_one_or_none()
            if definition and definition.current_version_id:
                version = await self.session.get(WorkflowDefinitionVersion, definition.current_version_id)
        if version is None or version.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow definition version not found")
        definition = await self.session.get(WorkflowDefinition, version.definition_id)
        if definition is None or str(definition.tenant_id) != str(self.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow definition not found")
        if entity_type != definition.entity_type:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "workflow entity_type does not match process definition")
        instance = WorkflowInstance(
            tenant_id=self.tenant_id,
            definition_id=definition.id,
            definition_version_id=version.id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=WorkflowInstanceStatus.RUNNING,
            started_by=actor_user_id,
            context_json=context,
            correlation_id=correlation_id,
        )
        self.session.add(instance)
        await self.session.flush()
        await self._append_event(instance.id, None, "instance_started", actor_user_id, {"entity_type": entity_type, "entity_id": entity_id})
        await self._advance(instance, actor_user_id=actor_user_id)
        return instance

    async def list_tasks(self, *, user_id: str | None, role_codes: list[str] | None = None) -> list[WorkflowTask]:
        stmt = select(WorkflowTask).where(WorkflowTask.tenant_id == self.tenant_id, WorkflowTask.deleted_at.is_(None), WorkflowTask.status == WorkflowTaskStatus.OPEN)
        if user_id:
            role_codes = role_codes or []
            stmt = stmt.where(or_(WorkflowTask.assignee_user_id == user_id, WorkflowTask.assignee_role_code.in_(role_codes)))
        return (await self.session.execute(stmt.order_by(WorkflowTask.due_at.asc().nullslast(), WorkflowTask.created_at.desc()))).scalars().all()

    async def complete_task(self, *, task_id: str, actor_user_id: str | None, actor_role_codes: list[str] | None, decision: str | None, payload: dict[str, Any] | None) -> WorkflowTask:
        task = await self.session.get(WorkflowTask, task_id)
        if task is None or task.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow task not found")
        if task.status != WorkflowTaskStatus.OPEN:
            raise HTTPException(status.HTTP_409_CONFLICT, "workflow task is not open")
        self._ensure_task_actor_allowed(task=task, actor_user_id=actor_user_id, actor_role_codes=actor_role_codes)
        task.status = WorkflowTaskStatus.COMPLETED
        task.completed_at = datetime.now(tz=timezone.utc)
        task.task_payload = {**(task.task_payload or {}), **(payload or {}), "decision": decision}
        instance = await self.session.get(WorkflowInstance, task.instance_id)
        if instance is None or str(instance.tenant_id) != str(self.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow instance not found")
        instance.context_json = {**(instance.context_json or {}), **(payload or {}), "last_decision": decision}
        await self._append_event(instance.id, task.node_id, "human_task_completed", actor_user_id, {"task_id": task.id, "decision": decision})
        await self._timeline_like_audit("workflow.task.complete", actor_user_id, task.id, {"instance_id": task.instance_id, "node_id": task.node_id, "decision": decision})
        await self._advance(instance, actor_user_id=actor_user_id, from_node_id=task.node_id)
        return task

    async def reassign_task(self, *, task_id: str, actor_user_id: str | None, actor_role_codes: list[str] | None, assignee_user_id: str | None, assignee_role_code: str | None, mode: str) -> WorkflowTask:
        task = await self.session.get(WorkflowTask, task_id)
        if task is None or task.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow task not found")
        if task.status != WorkflowTaskStatus.OPEN:
            raise HTTPException(status.HTTP_409_CONFLICT, "workflow task is not open")
        self._ensure_task_actor_allowed(task=task, actor_user_id=actor_user_id, actor_role_codes=actor_role_codes, allow_unassigned=True)
        if not assignee_user_id and not assignee_role_code:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "new assignee is required")
        if mode in {"delegate", "delegated", "escalate", "escalated"}:
            task.delegated_from_user_id = task.assignee_user_id
        task.assignee_user_id = assignee_user_id
        task.assignee_role_code = assignee_role_code
        task.status = WorkflowTaskStatus(mode)
        await self.session.flush()
        task.status = WorkflowTaskStatus.OPEN
        await self._append_event(task.instance_id, task.node_id, f"task_{mode}", actor_user_id, {"task_id": task.id, "assignee_user_id": assignee_user_id, "assignee_role_code": assignee_role_code})
        await self._timeline_like_audit(f"workflow.task.{mode}", actor_user_id, task.id, {"instance_id": task.instance_id, "node_id": task.node_id, "assignee_user_id": assignee_user_id, "assignee_role_code": assignee_role_code})
        return task

    async def get_instance_history(self, instance_id: str) -> tuple[WorkflowInstance, list[WorkflowTimelineEvent], list[WorkflowTask]]:
        instance = await self.session.get(WorkflowInstance, instance_id)
        if instance is None or instance.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow instance not found")
        events = (await self.session.execute(select(WorkflowTimelineEvent).where(WorkflowTimelineEvent.tenant_id == self.tenant_id, WorkflowTimelineEvent.instance_id == instance_id).order_by(WorkflowTimelineEvent.created_at.asc()))).scalars().all()
        tasks = (await self.session.execute(select(WorkflowTask).where(WorkflowTask.tenant_id == self.tenant_id, WorkflowTask.instance_id == instance_id).order_by(WorkflowTask.created_at.asc()))).scalars().all()
        return instance, events, tasks

    async def run_due_timers(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(tz=timezone.utc)
        rows = (await self.session.execute(select(WorkflowInstance).where(WorkflowInstance.tenant_id == self.tenant_id, WorkflowInstance.status.in_([WorkflowInstanceStatus.RUNNING, WorkflowInstanceStatus.WAITING]), WorkflowInstance.current_node_id.is_not(None)))).scalars().all()
        processed = 0
        for instance in rows:
            version = await self.session.get(WorkflowDefinitionVersion, instance.definition_version_id)
            if version is None or str(version.tenant_id) != str(self.tenant_id):
                continue
            node = self._node_map(version.graph_json).get(instance.current_node_id or "")
            if node and node.get("type") == "timer":
                due_at_raw = (instance.context_json or {}).get(f"timer_due::{node['id']}")
                if due_at_raw and datetime.fromisoformat(str(due_at_raw)) <= now:
                    await self._append_event(instance.id, node["id"], "timer_fired", None, {"due_at": due_at_raw})
                    await self._advance(instance, actor_user_id=None, from_node_id=node["id"])
                    processed += 1
        return processed

    async def _advance(self, instance: WorkflowInstance, *, actor_user_id: str | None, from_node_id: str | None = None) -> None:
        version = await self.session.get(WorkflowDefinitionVersion, instance.definition_version_id)
        if version is None or str(version.tenant_id) != str(self.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow version not found")
        graph = version.graph_json or {}
        node_map = self._node_map(graph)
        transitions = graph.get("transitions") or []
        start_node_id = from_node_id or next(node["id"] for node in graph.get("nodes") or [] if node.get("type") == "start")
        next_node_id = self._next_node_id(start_node_id, transitions, instance.context_json or {})
        while next_node_id:
            node = node_map[next_node_id]
            instance.current_node_id = next_node_id
            node_type = node.get("type")
            await self._append_event(instance.id, next_node_id, "node_entered", actor_user_id, {"node_type": node_type, "name": node.get("name")})
            if node_type in {"task", "approval"}:
                due_at = None
                if node.get("sla_hours"):
                    due_at = datetime.now(tz=timezone.utc) + timedelta(hours=int(node["sla_hours"]))
                task = WorkflowTask(
                    tenant_id=self.tenant_id,
                    instance_id=instance.id,
                    node_id=next_node_id,
                    title=str(node.get("name") or node_type),
                    assignee_user_id=node.get("assignee_user_id"),
                    assignee_role_code=node.get("assignee_role_code"),
                    due_at=due_at,
                    task_payload=node,
                )
                self.session.add(task)
                instance.status = WorkflowInstanceStatus.WAITING
                await self.session.flush()
                return
            if node_type == "condition":
                next_node_id = self._next_node_id(next_node_id, transitions, instance.context_json or {})
                continue
            if node_type == "timer":
                wait_minutes = int(node.get("delay_minutes") or 0)
                due_at = datetime.now(tz=timezone.utc) + timedelta(minutes=wait_minutes)
                instance.context_json = {**(instance.context_json or {}), f"timer_due::{next_node_id}": due_at.isoformat()}
                instance.status = WorkflowInstanceStatus.WAITING
                await self.session.flush()
                return
            if node_type in {"notification", "webhook", "integration_call"}:
                await self.outbox.add_event(
                    tenant_id=self.tenant_id,
                    event_type="WorkflowNodeTriggered",
                    aggregate_type="workflow_instance",
                    aggregate_id=instance.id,
                    payload={
                        "entity_type": instance.entity_type,
                        "entity_id": instance.entity_id,
                        "workflow_instance_id": instance.id,
                        "node_id": next_node_id,
                        "channel": node_type,
                        "destination": node.get("destination"),
                        "config": node,
                    },
                )
                await self._append_event(instance.id, next_node_id, f"{node_type}_queued", actor_user_id, {"destination": node.get("destination")})
                next_node_id = self._next_node_id(next_node_id, transitions, instance.context_json or {})
                continue
            if node_type == "end":
                instance.status = WorkflowInstanceStatus.COMPLETED
                instance.finished_at = datetime.now(tz=timezone.utc)
                await self._append_event(instance.id, next_node_id, "instance_completed", actor_user_id, {})
                await self.session.flush()
                return
            next_node_id = self._next_node_id(next_node_id, transitions, instance.context_json or {})
        instance.status = WorkflowInstanceStatus.COMPLETED
        instance.finished_at = datetime.now(tz=timezone.utc)

    def _next_node_id(self, current_node_id: str, transitions: list[dict[str, Any]], context: dict[str, Any]) -> str | None:
        options = [item for item in transitions if item.get("from") == current_node_id]
        if not options:
            return None
        for option in options:
            expression = option.get("when")
            if not expression:
                return option.get("to")
            if self._condition_matches(expression, context):
                return option.get("to")
        return options[0].get("to")

    @staticmethod
    def _condition_matches(expression: str, context: dict[str, Any]) -> bool:
        if "==" in expression:
            left, right = [part.strip() for part in expression.split("==", 1)]
            return str(context.get(left)) == right.strip("'\"")
        if "!=" in expression:
            left, right = [part.strip() for part in expression.split("!=", 1)]
            return str(context.get(left)) != right.strip("'\"")
        return bool(context.get(expression.strip()))

    @staticmethod
    def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(node.get("id")): node for node in graph.get("nodes") or [] if node.get("id")}

    async def _append_event(self, instance_id: str, node_id: str | None, event_type: str, actor_user_id: str | None, payload: dict[str, Any]) -> None:
        self.session.add(WorkflowTimelineEvent(tenant_id=self.tenant_id, instance_id=instance_id, node_id=node_id, event_type=event_type, actor_user_id=actor_user_id, payload=payload))
        await self.session.flush()

    async def _timeline_like_audit(self, action: str, actor_user_id: str | None, entity_id: str, details: dict[str, Any]) -> None:
        await self.audit.log_event(tenant_id=self.tenant_id, user_id=actor_user_id, action=action, object_type="workflow", object_id=entity_id, ip="system", details=details)

    @staticmethod
    def _ensure_task_actor_allowed(
        *,
        task: WorkflowTask,
        actor_user_id: str | None,
        actor_role_codes: list[str] | None = None,
        allow_unassigned: bool = False,
    ) -> None:
        if actor_user_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "workflow task requires authenticated actor")
        if task.assignee_user_id and str(task.assignee_user_id) != str(actor_user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "workflow task assigned to another user")
        if not task.assignee_user_id and task.assignee_role_code:
            actor_role_codes = actor_role_codes or []
            if task.assignee_role_code not in actor_role_codes and not allow_unassigned:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "workflow task requires matching role assignee")


    async def sweep_task_sla(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(tz=timezone.utc)
        rows = (await self.session.execute(select(WorkflowTask).where(WorkflowTask.tenant_id == self.tenant_id, WorkflowTask.status == WorkflowTaskStatus.OPEN, WorkflowTask.due_at.is_not(None), WorkflowTask.due_at <= now))).scalars().all()
        processed = 0
        for task in rows:
            if (task.task_payload or {}).get("sla_escalated"):
                continue
            task.task_payload = {**(task.task_payload or {}), "sla_escalated": True, "sla_escalated_at": now.isoformat()}
            await self._append_event(task.instance_id, task.node_id, "task_sla_escalated", None, {"task_id": task.id, "due_at": task.due_at.isoformat() if task.due_at else None})
            await self.outbox.add_event(tenant_id=self.tenant_id, event_type="WorkflowTaskEscalated", aggregate_type="workflow_task", aggregate_id=task.id, payload={"workflow_task_id": task.id, "workflow_instance_id": task.instance_id, "node_id": task.node_id, "assignee_user_id": task.assignee_user_id, "assignee_role_code": task.assignee_role_code, "due_at": task.due_at.isoformat() if task.due_at else None})
            processed += 1
        await self.session.flush()
        return processed
