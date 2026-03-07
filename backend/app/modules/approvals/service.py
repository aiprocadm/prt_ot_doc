from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ApprovalDecision,
    ApprovalInstance,
    ApprovalInstanceStatus,
    ApprovalInstanceStep,
    ApprovalInstanceStepStatus,
    ApprovalRoute,
    ApprovalRouteStep,
)


class ApprovalRouteService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id


class ApprovalInstanceService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def start(self, *, entity_type: str, entity_id: str, approval_route_id: str, started_by: str) -> ApprovalInstance:
        route = await self.session.get(ApprovalRoute, approval_route_id)
        if route is None or route.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval route not found")
        steps = (
            await self.session.execute(
                select(ApprovalRouteStep)
                .where(ApprovalRouteStep.approval_route_id == route.id, ApprovalRouteStep.tenant_id == self.tenant_id)
                .order_by(ApprovalRouteStep.order_no.asc())
            )
        ).scalars().all()
        if not steps:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Approval route has no steps")
        instance = ApprovalInstance(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            approval_route_id=approval_route_id,
            started_by=started_by,
            status=ApprovalInstanceStatus.RUNNING,
            started_at=datetime.now(tz=timezone.utc),
            current_step_no=steps[0].order_no,
        )
        self.session.add(instance)
        await self.session.flush()
        for step in steps:
            due_at = datetime.now(tz=timezone.utc) + timedelta(hours=step.deadline_hours) if step.deadline_hours else None
            self.session.add(
                ApprovalInstanceStep(
                    tenant_id=self.tenant_id,
                    approval_instance_id=instance.id,
                    route_step_id=step.id,
                    order_no=step.order_no,
                    assignee_user_id=step.user_id,
                    assignee_role_code=step.role_code,
                    due_at=due_at,
                    status=ApprovalInstanceStepStatus.PENDING,
                )
            )
        await self.session.flush()
        return instance


class ApprovalDecisionService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def decide(self, *, instance_id: str, actor_user_id: str, decision: str, comment: str | None = None, target_user_id: str | None = None) -> ApprovalInstance:
        instance = await self.session.get(ApprovalInstance, instance_id)
        if instance is None or instance.tenant_id != self.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval instance not found")
        step = (
            await self.session.execute(
                select(ApprovalInstanceStep)
                .where(
                    ApprovalInstanceStep.approval_instance_id == instance.id,
                    ApprovalInstanceStep.order_no == instance.current_step_no,
                    ApprovalInstanceStep.status == ApprovalInstanceStepStatus.PENDING,
                )
            )
        ).scalars().first()
        if step is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "No pending step")
        self.session.add(
            ApprovalDecision(
                tenant_id=self.tenant_id,
                approval_instance_id=instance.id,
                approval_instance_step_id=step.id,
                decision=decision,
                actor_user_id=actor_user_id,
                comment=comment,
            )
        )
        now = datetime.now(tz=timezone.utc)
        if decision == "comment":
            return instance
        if decision == "delegate":
            step.delegated_from_user_id = step.assignee_user_id
            step.assignee_user_id = target_user_id
            step.status = ApprovalInstanceStepStatus.DELEGATED
            return instance
        if decision == "reject":
            step.status = ApprovalInstanceStepStatus.REJECTED
            step.acted_at = now
            instance.status = ApprovalInstanceStatus.REJECTED
            instance.finished_at = now
            return instance
        step.status = ApprovalInstanceStepStatus.APPROVED
        step.acted_at = now
        next_step = (
            await self.session.execute(
                select(ApprovalInstanceStep)
                .where(ApprovalInstanceStep.approval_instance_id == instance.id, ApprovalInstanceStep.order_no > (instance.current_step_no or 0))
                .order_by(ApprovalInstanceStep.order_no.asc())
            )
        ).scalars().first()
        if next_step is None:
            instance.status = ApprovalInstanceStatus.APPROVED
            instance.current_step_no = None
            instance.finished_at = now
        else:
            instance.current_step_no = next_step.order_no
        return instance


class DelegationService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id


class EscalationService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id
