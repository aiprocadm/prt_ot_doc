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

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.role_labels import role_label
from app.models.compliance_requirements import (
    ComplianceRequirement,
    ComplianceRequirementEvidence,
)
from app.models.document import Document
from app.models.identity import User
from app.models.master_data import Company, Site
from app.models.npa import NpaAct, NpaClause

#: За сколько дней до контрольной даты требование попадает в Центр внимания
#: как «срок подходит» — то же окно, что у задач (``soon_threshold``).
DUE_SOON_DAYS = 3


def today() -> date:
    """«Сегодня» по UTC — теми же часами, что у остального продукта."""
    return datetime.now(tz=timezone.utc).date()


def is_overdue(row: ComplianceRequirement, reference: date | None = None) -> bool:
    # Параметр раньше звался ``today`` и затенял функцию: вызов без даты падал
    # с TypeError (срез-147). Ручки всегда передавали дату, поэтому не всплывало.
    reference = reference or today()
    return row.status == "active" and row.next_due_at is not None and row.next_due_at < reference


def days_left(row: ComplianceRequirement, reference: date | None = None) -> int | None:
    if row.next_due_at is None:
        return None
    return (row.next_due_at - (reference or today())).days


def display_name(user: User) -> str:
    """Как пользователь зовётся на витринах реестра: имя, без имени — почта."""
    return (user.full_name or "").strip() or user.email


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

    def _filtered(
        self,
        *,
        npa_id: str | None,
        status: str | None,
        only_overdue: bool,
        owner_user_id: str | None,
    ):
        """Общий отбор для страницы и для счётчиков.

        Один источник условий, а не два: разойдись они — и экран показывал бы
        «просрочено: 3» над страницей, где просроченных пять.
        """

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
        return stmt

    @staticmethod
    def _ordering():
        """Сначала то, что горит: активные по контрольной дате (без даты — в
        конец), потом закрытые и снятые; внутри — по коду.

        СРЕЗ-195: порядок переехал из памяти в базу. Сортировка после выборки
        означает, что выбрать надо ВСЁ, — то есть страницы невозможны в
        принципе: вторая страница по порядку, посчитанному в памяти, зависела бы
        от того, что уже прочитано.
        """

        status_rank = case((ComplianceRequirement.status == "active", 0), else_=1)
        return (
            status_rank,
            # NULLS LAST переносимо: булев признак «даты нет» сортируется первым
            # ключом, а сама дата — вторым. `nulls_last()` в SQLite не работает.
            ComplianceRequirement.next_due_at.is_(None),
            ComplianceRequirement.next_due_at,
            ComplianceRequirement.code,
        )

    async def list(
        self,
        *,
        npa_id: str | None = None,
        status: str | None = None,
        only_overdue: bool = False,
        owner_user_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ComplianceRequirement]:
        """Страница реестра. ``limit=None`` — всё (внутренние вызовы).

        Страничность добавлена срезом-195: до него ручка отдавала ВСЮ таблицу
        требований арендатора на каждое открытие экрана, а порядок считался в
        памяти после выборки.
        """

        stmt = self._filtered(
            npa_id=npa_id,
            status=status,
            only_overdue=only_overdue,
            owner_user_id=owner_user_id,
        ).order_by(*self._ordering())
        if limit is not None:
            stmt = stmt.limit(limit).offset(max(0, offset))
        return list((await self.session.execute(stmt)).scalars().all())

    async def counts(
        self,
        *,
        npa_id: str | None = None,
        status: str | None = None,
        only_overdue: bool = False,
        owner_user_id: str | None = None,
    ) -> dict[str, int]:
        """Счётчики по ВСЕЙ выборке, а не по выданной странице.

        Это главное требование среза. Счётчик, посчитанный по странице, — класс
        ошибки, который в проекте ловили дважды: человек видит «просрочено: 0»
        над первой страницей и считает, что просроченных нет вовсе.

        ``total`` считается при тех же фильтрах, ``active`` и ``overdue`` — при
        тех же фильтрах плюс своё условие: иначе «на контроле» на экране с
        фильтром «снятые» показывало бы число из другого мира.
        """

        base = self._filtered(
            npa_id=npa_id,
            status=status,
            only_overdue=only_overdue,
            owner_user_id=owner_user_id,
        ).subquery()

        total = await self.session.scalar(select(func.count()).select_from(base)) or 0
        active = (
            await self.session.scalar(
                select(func.count()).select_from(base).where(base.c.status == "active")
            )
            or 0
        )
        overdue = (
            await self.session.scalar(
                select(func.count())
                .select_from(base)
                .where(base.c.status == "active", base.c.next_due_at < today())
            )
            or 0
        )
        return {"total": int(total), "active": int(active), "overdue": int(overdue)}

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
        """Имена для ссылок: акт, пункт, ответственный, площадка — одним заходом на список.

        Возвращает ``{"acts": {id: {...}}, "clauses": {...}, "users": {...}, "sites": {...}}``.
        """
        act_ids = {r.npa_id for r in rows if r.npa_id}
        clause_ids = {r.clause_id for r in rows if r.clause_id}
        user_ids = {r.owner_user_id for r in rows if r.owner_user_id}
        site_ids = {r.site_id for r in rows if r.site_id}
        acts: dict[str, dict[str, Any]] = {}
        clauses: dict[str, dict[str, Any]] = {}
        users: dict[str, dict[str, Any]] = {}
        sites: dict[str, dict[str, Any]] = {}
        if site_ids:
            for site in (
                (
                    await self.session.execute(
                        select(Site).where(Site.tenant_id == self.tenant_id, Site.id.in_(site_ids))
                    )
                )
                .scalars()
                .all()
            ):
                sites[site.id] = {"name": site.name}
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
                users[user.id] = {"name": display_name(user)}
        return {"acts": acts, "clauses": clauses, "users": users, "sites": sites}

    async def owner_options(self) -> list[dict[str, str]]:
        """Кандидаты в ответственные: активные, не удалённые пользователи арендатора.

        Своя выборка, а не ``/admin/users``: та ручка — управление доступом
        (роли, атрибуты, почта) и открыта только admin/owner, а специалисту по
        ОТ для назначения ответственного нужны лишь имя и роль (срез-147).
        """
        rows = (
            (
                await self.session.execute(
                    select(User)
                    .where(
                        User.tenant_id == self.tenant_id,
                        User.deleted_at.is_(None),
                        User.is_active.is_(True),
                    )
                    .order_by(User.full_name, User.email)
                )
            )
            .scalars()
            .all()
        )
        options: list[dict[str, str]] = []
        for user in rows:
            code = str(getattr(user.role, "value", user.role))
            options.append(
                {
                    "id": user.id,
                    "name": display_name(user),
                    "role": code,
                    "role_label": role_label(code) or code,
                }
            )
        return options

    async def site_options(self) -> list[dict[str, str]]:
        """Площадки арендатора для привязки требования — с компанией, чтобы
        одноимённые цеха разных клиентов аутсорсера различались."""
        rows = (
            await self.session.execute(
                select(Site, Company.name)
                .join(Company, Company.id == Site.company_id)
                .where(Site.tenant_id == self.tenant_id, Site.deleted_at.is_(None))
                .order_by(Company.name, Site.name)
            )
        ).all()
        return [
            {"id": site.id, "name": site.name, "company_name": company_name}
            for site, company_name in rows
        ]

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
