from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
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

    @staticmethod
    def _value_matches(expected: object, actual: object) -> bool:
        if isinstance(expected, list):
            return actual in expected
        return expected == actual

    @classmethod
    def _matches_conditions(cls, conditions: dict[str, object], context: dict[str, object]) -> bool:
        for key, expected in conditions.items():
            if key == "amount_gte":
                actual = context.get("amount")
                if actual is None or not isinstance(actual, (int, float)) or actual < expected:
                    return False
                continue
            if key == "amount_lte":
                actual = context.get("amount")
                if actual is None or not isinstance(actual, (int, float)) or actual > expected:
                    return False
                continue
            if not cls._value_matches(expected, context.get(key)):
                return False
        return True

    async def resolve_route(
        self,
        *,
        applies_to: str,
        context: dict[str, object] | None = None,
    ) -> ApprovalRoute | None:
        stmt = select(ApprovalRoute).where(
            ApprovalRoute.tenant_id == self.tenant_id,
            ApprovalRoute.status == "active",
            or_(ApprovalRoute.applies_to == applies_to, ApprovalRoute.applies_to == "both"),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        context = context or {}
        matching = [
            row for row in rows if self._matches_conditions(row.conditions_json or {}, context)
        ]
        if matching:
            return matching[0]
        return next((row for row in rows if row.is_default), None)


class ApprovalInstanceService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def start(
        self, *, entity_type: str, entity_id: str, approval_route_id: str, started_by: str
    ) -> ApprovalInstance:
        route = await self.session.get(ApprovalRoute, approval_route_id)
        if route is None or str(route.tenant_id) != str(self.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval route not found")
        steps = (
            (
                await self.session.execute(
                    select(ApprovalRouteStep)
                    .where(
                        ApprovalRouteStep.approval_route_id == route.id,
                        ApprovalRouteStep.tenant_id == self.tenant_id,
                    )
                    .order_by(ApprovalRouteStep.order_no.asc())
                )
            )
            .scalars()
            .all()
        )
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
            if not step.user_id and not step.role_code:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Approval step requires assignee user_id or role_code",
                )
            due_at = (
                datetime.now(tz=timezone.utc) + timedelta(hours=step.deadline_hours)
                if step.deadline_hours
                else None
            )
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

    async def decide(
        self,
        *,
        instance_id: str,
        actor_user_id: str,
        decision: str,
        comment: str | None = None,
        target_user_id: str | None = None,
    ) -> ApprovalInstance:
        instance = await self.session.get(ApprovalInstance, instance_id)
        if instance is None or str(instance.tenant_id) != str(self.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval instance not found")
        step = (
            (
                await self.session.execute(
                    select(ApprovalInstanceStep).where(
                        ApprovalInstanceStep.tenant_id == self.tenant_id,
                        ApprovalInstanceStep.approval_instance_id == instance.id,
                        ApprovalInstanceStep.order_no == instance.current_step_no,
                        ApprovalInstanceStep.status == ApprovalInstanceStepStatus.PENDING,
                    )
                )
            )
            .scalars()
            .first()
        )
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
            if not target_user_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "target_user_id is required for delegate"
                )
            step.delegated_from_user_id = step.assignee_user_id
            step.assignee_user_id = target_user_id
            step.status = ApprovalInstanceStepStatus.PENDING
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
            (
                await self.session.execute(
                    select(ApprovalInstanceStep)
                    .where(
                        ApprovalInstanceStep.tenant_id == self.tenant_id,
                        ApprovalInstanceStep.approval_instance_id == instance.id,
                        ApprovalInstanceStep.order_no > (instance.current_step_no or 0),
                    )
                    .order_by(ApprovalInstanceStep.order_no.asc())
                )
            )
            .scalars()
            .first()
        )
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

    async def escalate_overdue(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(tz=timezone.utc)
        rows = (
            await self.session.execute(
                select(ApprovalInstanceStep, ApprovalRouteStep)
                .join(ApprovalRouteStep, ApprovalRouteStep.id == ApprovalInstanceStep.route_step_id)
                .where(
                    ApprovalInstanceStep.tenant_id == self.tenant_id,
                    ApprovalInstanceStep.status == ApprovalInstanceStepStatus.PENDING,
                    ApprovalInstanceStep.due_at.is_not(None),
                    ApprovalInstanceStep.due_at < now,
                    or_(
                        ApprovalRouteStep.escalation_user_id.is_not(None),
                        ApprovalRouteStep.escalation_role_code.is_not(None),
                    ),
                )
            )
        ).all()
        updated = 0
        for step, route_step in rows:
            step.delegated_from_user_id = step.assignee_user_id
            if route_step.escalation_user_id:
                step.assignee_user_id = route_step.escalation_user_id
            if route_step.escalation_role_code:
                step.assignee_role_code = route_step.escalation_role_code
            updated += 1
        if updated:
            await self.session.flush()
        return updated
