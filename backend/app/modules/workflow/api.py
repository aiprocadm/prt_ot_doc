from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant
from app.modules.workflow.models import WorkflowDefinitionStatus, WorkflowInstanceStatus, WorkflowTaskStatus
from app.modules.workflow.service import WorkflowService

router = APIRouter(prefix="/workflow", tags=["workflow"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AccessDep = Annotated[AccessContext, Depends(rbac())]


class WorkflowDefinitionIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    entity_type: str
    graph: dict[str, Any]
    variables_schema: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")


class WorkflowVersionRead(BaseModel):
    id: str
    definition_id: str
    version_no: int
    status: str
    graph_json: dict[str, Any]
    variables_schema: dict[str, Any]


class WorkflowDefinitionRead(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    entity_type: str
    current_version_id: str | None = None
    versions: list[WorkflowVersionRead] = Field(default_factory=list)


class WorkflowStartIn(BaseModel):
    definition_code: str | None = None
    version_id: str | None = None
    entity_type: str
    entity_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class WorkflowTaskActionIn(BaseModel):
    decision: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    assignee_user_id: str | None = None
    assignee_role_code: str | None = None


class WorkflowTaskRead(BaseModel):
    id: str
    instance_id: str
    node_id: str
    title: str
    assignee_user_id: str | None = None
    assignee_role_code: str | None = None
    status: str
    due_at: str | None = None
    completed_at: str | None = None
    task_payload: dict[str, Any]


class WorkflowTimelineRead(BaseModel):
    id: str
    node_id: str | None = None
    event_type: str
    actor_user_id: str | None = None
    payload: dict[str, Any]
    created_at: str


class WorkflowInstanceRead(BaseModel):
    id: str
    definition_id: str
    definition_version_id: str
    entity_type: str
    entity_id: str
    status: str
    current_node_id: str | None = None
    context_json: dict[str, Any]
    correlation_id: str | None = None
    timeline: list[WorkflowTimelineRead] = Field(default_factory=list)
    tasks: list[WorkflowTaskRead] = Field(default_factory=list)


def _service(session: AsyncSession, tenant: Tenant) -> WorkflowService:
    return WorkflowService(session, str(tenant.id))


def _serialize_version(item) -> WorkflowVersionRead:
    return WorkflowVersionRead(id=item.id, definition_id=item.definition_id, version_no=item.version_no, status=item.status.value if hasattr(item.status, 'value') else str(item.status), graph_json=item.graph_json or {}, variables_schema=item.variables_schema or {})


def _serialize_task(item) -> WorkflowTaskRead:
    return WorkflowTaskRead(id=item.id, instance_id=item.instance_id, node_id=item.node_id, title=item.title, assignee_user_id=item.assignee_user_id, assignee_role_code=item.assignee_role_code, status=item.status.value if hasattr(item.status, 'value') else str(item.status), due_at=item.due_at.isoformat() if item.due_at else None, completed_at=item.completed_at.isoformat() if item.completed_at else None, task_payload=item.task_payload or {})


@router.post("/definitions", response_model=WorkflowVersionRead, status_code=status.HTTP_201_CREATED)
async def create_definition(payload: WorkflowDefinitionIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowVersionRead:
    version = await _service(session, tenant).create_definition(code=payload.code, name=payload.name, description=payload.description, entity_type=payload.entity_type, graph=payload.graph, variables_schema=payload.variables_schema, actor_user_id=access.user.id)
    await session.commit()
    return _serialize_version(version)


@router.post("/definitions/validate")
async def validate_definition(payload: WorkflowDefinitionIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> dict[str, Any]:
    _ = access
    _service(session, tenant).validate_graph(payload.graph)
    return {"valid": True, "node_types": sorted({str(node.get('type')) for node in payload.graph.get('nodes') or []})}


@router.get("/definitions", response_model=list[WorkflowDefinitionRead])
async def list_definitions(session: SessionDep, tenant: TenantDep, access: AccessDep) -> list[WorkflowDefinitionRead]:
    _ = access
    service = _service(session, tenant)
    definitions = await service.list_definitions()
    result: list[WorkflowDefinitionRead] = []
    for item in definitions:
        versions = await service.get_versions(item.id)
        result.append(WorkflowDefinitionRead(id=item.id, code=item.code, name=item.name, description=item.description, entity_type=item.entity_type, current_version_id=item.current_version_id, versions=[_serialize_version(v) for v in versions]))
    return result


@router.post("/versions/{version_id}/publish", response_model=WorkflowVersionRead)
async def publish_version(version_id: str, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowVersionRead:
    version = await _service(session, tenant).publish_version(version_id, access.user.id)
    await session.commit()
    return _serialize_version(version)


@router.post("/versions/{version_id}/archive", response_model=WorkflowVersionRead)
async def archive_version(version_id: str, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowVersionRead:
    version = await _service(session, tenant).archive_version(version_id, access.user.id)
    await session.commit()
    return _serialize_version(version)


@router.post("/instances", response_model=WorkflowInstanceRead, status_code=status.HTTP_201_CREATED)
async def start_instance(payload: WorkflowStartIn, response: Response, x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"), session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), access: AccessContext = Depends(rbac())) -> WorkflowInstanceRead:
    instance = await _service(session, tenant).start_instance(definition_code=payload.definition_code, version_id=payload.version_id, entity_type=payload.entity_type, entity_id=payload.entity_id, context=payload.context, actor_user_id=access.user.id, correlation_id=x_correlation_id)
    await session.commit()
    _, timeline, tasks = await _service(session, tenant).get_instance_history(instance.id)
    response.headers["X-Correlation-ID"] = x_correlation_id or instance.correlation_id or instance.id
    return WorkflowInstanceRead(id=instance.id, definition_id=instance.definition_id, definition_version_id=instance.definition_version_id, entity_type=instance.entity_type, entity_id=instance.entity_id, status=instance.status.value if hasattr(instance.status, 'value') else str(instance.status), current_node_id=instance.current_node_id, context_json=instance.context_json or {}, correlation_id=instance.correlation_id, timeline=[WorkflowTimelineRead(id=e.id, node_id=e.node_id, event_type=e.event_type, actor_user_id=e.actor_user_id, payload=e.payload or {}, created_at=e.created_at.isoformat()) for e in timeline], tasks=[_serialize_task(t) for t in tasks])


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceRead)
async def get_instance(instance_id: str, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowInstanceRead:
    _ = access
    instance, timeline, tasks = await _service(session, tenant).get_instance_history(instance_id)
    return WorkflowInstanceRead(id=instance.id, definition_id=instance.definition_id, definition_version_id=instance.definition_version_id, entity_type=instance.entity_type, entity_id=instance.entity_id, status=instance.status.value if hasattr(instance.status, 'value') else str(instance.status), current_node_id=instance.current_node_id, context_json=instance.context_json or {}, correlation_id=instance.correlation_id, timeline=[WorkflowTimelineRead(id=e.id, node_id=e.node_id, event_type=e.event_type, actor_user_id=e.actor_user_id, payload=e.payload or {}, created_at=e.created_at.isoformat()) for e in timeline], tasks=[_serialize_task(t) for t in tasks])


@router.get("/tasks", response_model=list[WorkflowTaskRead])
async def list_tasks(session: SessionDep, tenant: TenantDep, access: AccessDep, assignee: str | None = Query(default="me")) -> list[WorkflowTaskRead]:
    role_codes = [role.code for role in getattr(access.user, 'roles', [])] if getattr(access.user, 'roles', None) else []
    tasks = await _service(session, tenant).list_tasks(user_id=access.user.id if assignee == 'me' else None, role_codes=role_codes)
    return [_serialize_task(item) for item in tasks]


@router.post("/tasks/{task_id}/complete", response_model=WorkflowTaskRead)
async def complete_task(task_id: str, payload: WorkflowTaskActionIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowTaskRead:
    task = await _service(session, tenant).complete_task(task_id=task_id, actor_user_id=access.user.id, actor_role_codes=[role.code for role in getattr(access.user, 'roles', [])] if getattr(access.user, 'roles', None) else [], decision=payload.decision, payload=payload.payload)
    await session.commit()
    return _serialize_task(task)


@router.post("/tasks/{task_id}/reassign", response_model=WorkflowTaskRead)
async def reassign_task(task_id: str, payload: WorkflowTaskActionIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowTaskRead:
    task = await _service(session, tenant).reassign_task(task_id=task_id, actor_user_id=access.user.id, actor_role_codes=[role.code for role in getattr(access.user, 'roles', [])] if getattr(access.user, 'roles', None) else [], assignee_user_id=payload.assignee_user_id, assignee_role_code=payload.assignee_role_code, mode="reassigned")
    await session.commit()
    return _serialize_task(task)


@router.post("/tasks/{task_id}/delegate", response_model=WorkflowTaskRead)
async def delegate_task(task_id: str, payload: WorkflowTaskActionIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowTaskRead:
    task = await _service(session, tenant).reassign_task(task_id=task_id, actor_user_id=access.user.id, actor_role_codes=[role.code for role in getattr(access.user, 'roles', [])] if getattr(access.user, 'roles', None) else [], assignee_user_id=payload.assignee_user_id, assignee_role_code=payload.assignee_role_code, mode="delegated")
    await session.commit()
    return _serialize_task(task)


@router.post("/tasks/{task_id}/escalate", response_model=WorkflowTaskRead)
async def escalate_task(task_id: str, payload: WorkflowTaskActionIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowTaskRead:
    task = await _service(session, tenant).reassign_task(task_id=task_id, actor_user_id=access.user.id, actor_role_codes=[role.code for role in getattr(access.user, 'roles', [])] if getattr(access.user, 'roles', None) else [], assignee_user_id=payload.assignee_user_id, assignee_role_code=payload.assignee_role_code, mode="escalated")
    await session.commit()
    return _serialize_task(task)


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionRead)
async def get_definition(definition_id: str, session: SessionDep, tenant: TenantDep, access: AccessDep) -> WorkflowDefinitionRead:
    _ = access
    service = _service(session, tenant)
    definitions = await service.list_definitions()
    item = next((definition for definition in definitions if definition.id == definition_id), None)
    if item is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="workflow definition not found")
    versions = await service.get_versions(item.id)
    return WorkflowDefinitionRead(id=item.id, code=item.code, name=item.name, description=item.description, entity_type=item.entity_type, current_version_id=item.current_version_id, versions=[_serialize_version(v) for v in versions])
