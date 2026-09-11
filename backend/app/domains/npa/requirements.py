"""Реестр требований арендатора (B.18 разд. 19.2, срез-145).

Служба держит все правила «что значит просрочено» и «что делает подтверждение»
в одном месте, чтобы ручки, оценка влияния (разд. 19.3) и Центр внимания
считали одинаково:

* «сегодня» — по UTC, как во всём продукте (срез-140), не по часовому поясу
  процесса;
* просрочено = контрольная дата раньше сегодняшней И требование активно;
  закрытые и снятые с контроля не бывают просроченными;
* доказательство исполнения с периодичностью сдвигает контрольную дату на
  период от дня подтверждения (не от старой даты: если исполнили с опозданием,
  следующий срок считается от факта, иначе просрочка накапливается вечно);
  без периодичности — требование разовое и закрывается.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.compliance_requirements import (
    ComplianceRequirement,
    ComplianceRequirementEvidence,
)
from app.models.document import Document
from app.models.identity import User
from app.models.npa import NpaAct, NpaClause

#: За сколько дней до контрольной даты требование попадает в Центр внимания
#: как «срок подходит» — то же окно, что у задач (``soon_threshold``).
DUE_SOON_DAYS = 3


def today() -> date:
    """«Сегодня» по UTC — теми же часами, что у остального продукта."""
    return datetime.now(tz=timezone.utc).date()


def is_overdue(row: ComplianceRequirement, today: date | None = None) -> bool:
    today = today or today()
    return row.status == "active" and row.next_due_at is not None and row.next_due_at < today


def days_left(row: ComplianceRequirement, today: date | None = None) -> int | None:
    if row.next_due_at is None:
        return None
    return (row.next_due_at - (today or today())).days


@dataclass(slots=True)
class RequirementAttention:
    """Одна строка Центра внимания: требование просрочено или срок подходит."""

    requirement_id: str
    code: str
    title: str
    severity: str
    next_due_at: date
    overdue: bool
    owner_user_id: str | None


@dataclass(slots=True)
class RequirementsService:
    session: AsyncSession
    tenant_id: str

    async def list(
        self,
        *,
        npa_id: str | None = None,
        status: str | None = None,
        only_overdue: bool = False,
        owner_user_id: str | None = None,
    ) -> list[ComplianceRequirement]:
        stmt = select(ComplianceRequirement).where(
            ComplianceRequirement.tenant_id == self.tenant_id
        )
        if npa_id:
            stmt = stmt.where(ComplianceRequirement.npa_id == npa_id)
        if status:
            stmt = stmt.where(ComplianceRequirement.status == status)
        if owner_user_id:
            stmt = stmt.where(ComplianceRequirement.owner_user_id == owner_user_id)
        if only_overdue:
            stmt = stmt.where(
                ComplianceRequirement.status == "active",
                ComplianceRequirement.next_due_at < today(),
            )
        # Сначала то, что горит: активные по контрольной дате (без даты — в
        # конец), потом закрытые и снятые; внутри — по коду.
        rows = list((await self.session.execute(stmt)).scalars().all())
        rows.sort(
            key=lambda r: (
                0 if r.status == "active" else 1,
                r.next_due_at is None,
                r.next_due_at or date.max,
                r.code,
            )
        )
        return rows

    async def get(self, requirement_id: str) -> ComplianceRequirement | None:
        return await self.session.scalar(
            select(ComplianceRequirement)
            .options(selectinload(ComplianceRequirement.evidence))
            .where(
                ComplianceRequirement.id == requirement_id,
                ComplianceRequirement.tenant_id == self.tenant_id,
            )
        )

    async def evidence_counts(self, rows: list[ComplianceRequirement]) -> dict[str, int]:
        if not rows:
            return {}
        result = await self.session.execute(
            select(
                ComplianceRequirementEvidence.requirement_id,
                func.count(ComplianceRequirementEvidence.id),
            )
            .where(
                ComplianceRequirementEvidence.tenant_id == self.tenant_id,
                ComplianceRequirementEvidence.requirement_id.in_([r.id for r in rows]),
            )
            .group_by(ComplianceRequirementEvidence.requirement_id)
        )
        return {requirement_id: int(count) for requirement_id, count in result.all()}

    async def confirm(
        self,
        row: ComplianceRequirement,
        *,
        confirmed_by: str | None,
        document_id: str | None,
        note: str | None,
        confirmed_at: date | None,
    ) -> ComplianceRequirementEvidence:
        """Записать доказательство и сдвинуть (или закрыть) контроль.

        Подтверждать можно и закрытое, и снятое требование — доказательство
        задним числом на проверке важнее чистоты статуса; но статус и даты у
        таких строк не трогаем: у снятого с контроля срока нет.
        """
        when = confirmed_at or today()
        evidence = ComplianceRequirementEvidence(
            tenant_id=self.tenant_id,
            requirement_id=row.id,
            document_id=document_id,
            note=note,
            confirmed_at=when,
            confirmed_by=confirmed_by,
        )
        self.session.add(evidence)
        if row.status == "active":
            if row.last_confirmed_at is None or row.last_confirmed_at < when:
                row.last_confirmed_at = when
            if row.periodicity_days:
                row.next_due_at = when + timedelta(days=row.periodicity_days)
            else:
                row.status = "fulfilled"
        return evidence

    def retire(self, row: ComplianceRequirement) -> None:
        row.status = "retired"
        row.retired_at = datetime.now(tz=timezone.utc)

    async def attention(self, *, owner_user_id: str | None = None) -> list[RequirementAttention]:
        """Активные требования, которые просрочены или подходят к сроку.

        ``owner_user_id`` сужает до чужих-невидимых: роли без обзора по
        арендатору видят только то, за что отвечают сами.
        """
        reference = today()
        horizon = reference + timedelta(days=DUE_SOON_DAYS)
        stmt = select(ComplianceRequirement).where(
            ComplianceRequirement.tenant_id == self.tenant_id,
            ComplianceRequirement.status == "active",
            ComplianceRequirement.next_due_at.is_not(None),
            ComplianceRequirement.next_due_at <= horizon,
        )
        if owner_user_id is not None:
            stmt = stmt.where(ComplianceRequirement.owner_user_id == owner_user_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            RequirementAttention(
                requirement_id=row.id,
                code=row.code,
                title=row.title,
                severity=row.severity,
                next_due_at=row.next_due_at,  # type: ignore[arg-type]
                overdue=row.next_due_at < reference,  # type: ignore[operator]
                owner_user_id=row.owner_user_id,
            )
            for row in sorted(rows, key=lambda r: (r.next_due_at, r.code))  # type: ignore[arg-type]
        ]

    async def active_for_act(self, act_id: str) -> list[ComplianceRequirement]:
        """Активные требования из акта — для оценки влияния (разд. 19.3)."""
        rows = await self.list(npa_id=act_id, status="active")
        return rows

    async def references(
        self, rows: list[ComplianceRequirement]
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Имена для ссылок: акт, пункт, ответственный — одним заходом на список.

        Возвращает ``{"acts": {id: {...}}, "clauses": {...}, "users": {...}}``.
        """
        act_ids = {r.npa_id for r in rows if r.npa_id}
        clause_ids = {r.clause_id for r in rows if r.clause_id}
        user_ids = {r.owner_user_id for r in rows if r.owner_user_id}
        acts: dict[str, dict[str, Any]] = {}
        clauses: dict[str, dict[str, Any]] = {}
        users: dict[str, dict[str, Any]] = {}
        if act_ids:
            for act in (
                (await self.session.execute(select(NpaAct).where(NpaAct.id.in_(act_ids))))
                .scalars()
                .all()
            ):
                acts[act.id] = {"code": act.code, "title": act.title}
        if clause_ids:
            for clause in (
                (await self.session.execute(select(NpaClause).where(NpaClause.id.in_(clause_ids))))
                .scalars()
                .all()
            ):
                clauses[clause.id] = {"code": clause.code}
        if user_ids:
            for user in (
                (
                    await self.session.execute(
                        select(User).where(User.tenant_id == self.tenant_id, User.id.in_(user_ids))
                    )
                )
                .scalars()
                .all()
            ):
                users[user.id] = {"name": user.full_name or user.email}
        return {"acts": acts, "clauses": clauses, "users": users}

    async def document_titles(self, document_ids: set[str]) -> dict[str, str]:
        """«Шаблон · Компания» — так документы зовутся на всех витринах НПА."""
        if not document_ids:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(Document)
                    .options(selectinload(Document.template), selectinload(Document.company))
                    .where(Document.tenant_id == self.tenant_id, Document.id.in_(document_ids))
                )
            )
            .scalars()
            .all()
        )
        titles: dict[str, str] = {}
        for document in rows:
            name = document.template.name if document.template else "Документ"
            company = document.company.name if document.company else None
            titles[document.id] = f"{name} · {company}" if company else name
        return titles
