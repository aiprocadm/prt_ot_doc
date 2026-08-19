from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.disciplines import (
    ATTENTION_SOURCES,
    DISCIPLINE_TITLES,
    MEASURED_DISCIPLINES,
    UNCLASSIFIED_SOURCES,
    UNMEASURED_DISCIPLINES,
    Discipline,
    discipline_of,
)
from app.core.security import AccessContext, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.finance import Contract, ContractStatus
from app.models.models import (
    ComplianceDeadline,
    Incident,
    IncidentStatus,
    Inspection,
    InspectionStatus,
    OfflineSyncBatch,
    Person,
    PPEIssue,
    PPEIssueStatus,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
    TrainingEnrollment,
)
from app.models.obligations import Task, TaskStatus
from app.schemas.calendar import CalendarEventItem
from app.services.calendar_aggregator import CalendarAggregatorService
from app.services.person_link import resolve_person_id

router = APIRouter(prefix="/workspace", tags=["workspace"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AccessDep = Annotated[AccessContext, Depends(rbac())]


class AttentionSummary(BaseModel):
    overdue_tasks: int = 0
    due_soon_tasks: int = 0
    overdue_deadlines: int = 0
    pending_sync_batches: int = 0
    failed_sync_batches: int = 0
    readiness_blockers: int = 0


class ReadinessBlocker(BaseModel):
    code: str
    title: str
    severity: str
    count: int
    reason: str
    entity_type: str
    action_hint: str


class AttentionItem(BaseModel):
    item_type: str
    id: str
    severity: str
    title: str
    status: str
    due_at: datetime | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    reason: str
    #: Дисциплина записи (BIZ-54-57 срез-1, разд. 57.2). ``None`` у задач и у
    #: источников, которые дисциплину не хранят, — см. ``core/disciplines.py``.
    discipline: str | None = None


class DisciplineAttention(BaseModel):
    """Строка сводки по дисциплине (разд. 57.2).

    ``measured=False`` — не «ноль нарушений», а «мы это не считаем»: показать
    по неизмеряемой дисциплине ноль значило бы объявить благополучие там, где
    данных нет (то же правило, что у светофора клиента в BIZ-51).
    """

    code: str
    title: str
    measured: bool
    overdue: int = 0
    due_soon: int = 0
    reason: str | None = None


class WorkspaceAttentionResponse(BaseModel):
    generated_at: datetime
    summary: AttentionSummary
    items: list[AttentionItem] = Field(default_factory=list)
    blockers: list[ReadinessBlocker] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    #: Разрез по дисциплинам ТЗ. Поле необязательное: старые клиенты его просто
    #: не читают.
    disciplines: list[DisciplineAttention] = Field(default_factory=list)
    #: Источники, у которых дисциплина не хранится, — названы с причиной, а не
    #: спрятаны: «источника нет» и «источник намеренно не размечен» — разное.
    unclassified_sources: list[str] = Field(default_factory=list)
    #: Показаны не все записи (сработал лимит). Молча обрезанный список читался
    #: бы как полный, а «скоро срок» тогда занижен.
    items_truncated: bool = False


class TaskInboxItem(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    due_at: datetime | None = None
    assignee_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    overdue: bool = False


class WorkspaceTaskInboxResponse(BaseModel):
    total: int
    overdue: int
    items: list[TaskInboxItem] = Field(default_factory=list)


def _worker_like_role(role: str) -> bool:
    return role in {"worker", "client_user"}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


#: Насколько глубоко в прошлое смотрит Центр внимания. Просрочку двухлетней
#: давности он не покажет: это уже не «внимание», а разбор архива, и такой
#: запрос стоил бы посадочной странице лишних строк на каждый источник.
_DISCIPLINE_LOOKBACK = timedelta(days=180)

#: Полосы SLA, которые агрегатор считает поводом для внимания. ``warning`` и
#: ``ok`` сюда не входят — иначе список превратился бы в копию календаря.
_ATTENTION_BANDS = {"overdue", "critical"}

#: Роли, которым видны ЧУЖИЕ записи дисциплин. Список копирует
#: ``_CALENDAR_READ_ROLES`` календаря намеренно: медосмотры, направления, СИЗ,
#: обучение и инструктажи — поимённый учёт, и Центр внимания не имеет права
#: показывать их шире, чем профильные экраны. Иначе «центр внимания» стал бы
#: боковым каналом к данным, которые в модуле СИЗ отдаются одному админу.
#: Всем прочим ролям подмешиваются ТОЛЬКО их собственные записи.
_DISCIPLINE_TENANT_WIDE_ROLES = frozenset(
    {
        "admin",
        "owner",
        "hr",
        "line_manager",
        "ot_pb_lead",
        "ot_specialist",
        "pb_engineer",
        "ecologist",
    }
)


class _DisciplineFacts:
    """События внимания и ЧЕСТНЫЕ итоги по дисциплинам.

    Список и счётчики разделены намеренно: ``items`` обрезаются лимитом (экран
    не читает тысячу строк), а числа берутся из ``by_source`` — это те же
    ``COUNT``, что агрегатор уже посчитал. Считать «просрочено» по обрезанному
    списку значило бы показать размер страницы вместо количества: при
    тридцати семи просроченных медосмотрах и лимите 30 экран написал бы «29»,
    а целая дисциплина, чьи строки не влезли, ушла бы в зелёный ноль.
    """

    def __init__(
        self, events: list[CalendarEventItem], overdue: dict[Discipline, int], shown: int
    ) -> None:
        self.events = events
        self.overdue = overdue
        self.truncated = shown > len(events)


async def _discipline_events(
    *,
    session: AsyncSession,
    tenant: Tenant,
    person_id: str | None,
    now: datetime,
    limit: int,
) -> _DisciplineFacts:
    """Просрочки и близкие сроки по дисциплинам — из общего агрегатора.

    Свои SQL-запросы здесь не пишутся намеренно: что считается просрочкой
    медосмотра или выдачи СИЗ, уже решено в ``CalendarAggregatorService`` и
    покрыто его тестами. Вторая формула рядом разошлась бы с календарём, и два
    экрана показывали бы про одного человека разное.

    Запрашиваются ТОЛЬКО размеченные источники (``ATTENTION_SOURCES``):
    у остальных дисциплина не хранится, и их строки некуда отнести.
    """

    service = CalendarAggregatorService(tenant_id=str(tenant.id), db=session)
    response = await service.list_events(
        from_at=now - _DISCIPLINE_LOOKBACK,
        to_at=now + timedelta(days=3),
        source_types=ATTENTION_SOURCES,
        person_id=person_id,
        include_sla=True,
    )

    # Честные итоги: сумма COUNT'ов источников, а не длина показанного списка.
    overdue: dict[Discipline, int] = {}
    for source in response.by_source:
        discipline = discipline_of(source.source_type)
        if discipline is None:
            continue
        overdue[discipline] = overdue.get(discipline, 0) + int(source.overdue_count or 0)

    events = [item for item in response.items if item.sla_band in _ATTENTION_BANDS]
    # Просроченное вперёд: с него начинают работу, а близкий срок подождёт.
    # Признак берём у самого события (``is_overdue``), а не у полосы SLA: полоса
    # говорит лишь «дата в прошлом», поэтому возвращённый СИЗ и завершённое
    # обучение с прошедшим сроком попадали бы в просрочку, хотя закрыты.
    events.sort(key=lambda item: (not item.is_overdue, item.starts_at))
    return _DisciplineFacts(events[:limit], overdue, shown=len(events))


async def _readiness_blockers(
    *,
    session: AsyncSession,
    tenant: Tenant,
    now: datetime,
) -> list[ReadinessBlocker]:
    blockers: list[ReadinessBlocker] = []

    missing_employee_contacts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Person)
                .where(
                    Person.tenant_id == tenant.id,
                    Person.deleted_at.is_(None),
                    or_(Person.email.is_(None), Person.phone.is_(None)),
                )
            )
        ).scalar_one()
        or 0
    )
    if missing_employee_contacts > 0:
        blockers.append(
            ReadinessBlocker(
                code="employees_missing_contacts",
                title="Неполные контакты сотрудников",
                severity="high",
                count=missing_employee_contacts,
                reason="Без email или телефона ломаются уведомления и назначения (обучение, задачи, СИЗ)",
                entity_type="person",
                action_hint="Заполните email и телефон в карточках сотрудников",
            )
        )

    ready_template_versions = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TemplateVersion)
                .where(
                    TemplateVersion.tenant_id == tenant.id,
                    TemplateVersion.deleted_at.is_(None),
                    TemplateVersion.status.in_(
                        [
                            TemplateVersionStatus.ACTIVE,
                            TemplateVersionStatus.READY,
                            TemplateVersionStatus.LINTED,
                        ]
                    ),
                )
            )
        ).scalar_one()
        or 0
    )
    if ready_template_versions == 0:
        blockers.append(
            ReadinessBlocker(
                code="templates_not_ready",
                title="Нет готовых шаблонов",
                severity="critical",
                count=1,
                reason="Без активной версии шаблона недоступен жизненный цикл документов",
                entity_type="template_version",
                action_hint="Загрузите шаблон, проверьте линтером и активируйте версию",
            )
        )

    overdue_training = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TrainingEnrollment)
                .where(
                    TrainingEnrollment.tenant_id == tenant.id,
                    TrainingEnrollment.deleted_at.is_(None),
                    TrainingEnrollment.status.in_(["assigned", "in_progress"]),
                    TrainingEnrollment.due_at.is_not(None),
                    TrainingEnrollment.due_at < now,
                )
            )
        ).scalar_one()
        or 0
    )
    if overdue_training > 0:
        blockers.append(
            ReadinessBlocker(
                code="training_overdue",
                title="Просроченные назначения обучения",
                severity="high",
                count=overdue_training,
                reason="Просрочка снижает готовность и повышает регуляторные риски",
                entity_type="training_enrollment",
                action_hint="Закройте просроченные назначения или перенесите сроки",
            )
        )

    expired_ppe = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PPEIssue)
                .where(
                    PPEIssue.tenant_id == tenant.id,
                    PPEIssue.deleted_at.is_(None),
                    PPEIssue.status == PPEIssueStatus.ISSUED,
                    PPEIssue.expires_at.is_not(None),
                    PPEIssue.expires_at < now,
                )
            )
        ).scalar_one()
        or 0
    )
    if expired_ppe > 0:
        blockers.append(
            ReadinessBlocker(
                code="ppe_expired",
                title="Просроченная выданная СИЗ",
                severity="high",
                count=expired_ppe,
                reason="Истёкший срок СИЗ означает незакрытые обязанности по замене или возврату",
                entity_type="ppe_issue",
                action_hint="Выдайте замену или отметьте возврат/утрату",
            )
        )

    expired_active_contracts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Contract)
                .where(
                    Contract.tenant_id == tenant.id,
                    Contract.deleted_at.is_(None),
                    Contract.status == ContractStatus.ACTIVE,
                    Contract.valid_until.is_not(None),
                    Contract.valid_until < date.today(),
                )
            )
        ).scalar_one()
        or 0
    )
    if expired_active_contracts > 0:
        blockers.append(
            ReadinessBlocker(
                code="contracts_expired",
                title="Истёкшие активные договоры",
                severity="critical",
                count=expired_active_contracts,
                reason="Просроченный договор ломает готовность контрагентов и сценарии пакетов",
                entity_type="contract",
                action_hint="Закройте договор или продлите срок действия",
            )
        )

    return blockers


@router.get("/attention", response_model=WorkspaceAttentionResponse)
async def workspace_attention(
    tenant: TenantDep,
    session: SessionDep,
    access: AccessDep,
    # Annotated-форма обязательна: тесты зовут обработчик НАПРЯМУЮ, и при
    # `limit: int = Query(30)` внутрь приезжает объект Query вместо числа
    # (грабля репо, стоившая волне BIZ-50 трёх падений регресса).
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> WorkspaceAttentionResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    now = datetime.now(timezone.utc)
    soon_threshold = now + timedelta(days=3)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]

    task_stmt = select(Task).where(
        Task.tenant_id == tenant.id,
        Task.status.in_(open_statuses),
    )
    if _worker_like_role(access.user.role.value):
        task_stmt = task_stmt.where(Task.assignee_id == access.user.id)

    overdue_task_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.tenant_id == tenant.id,
                    Task.status.in_(open_statuses),
                    Task.due_at.is_not(None),
                    Task.due_at < now,
                    (
                        Task.assignee_id == access.user.id
                        if _worker_like_role(access.user.role.value)
                        else True
                    ),
                )
            )
        ).scalar_one()
        or 0
    )
    due_soon_task_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.tenant_id == tenant.id,
                    Task.status.in_(open_statuses),
                    Task.due_at.is_not(None),
                    Task.due_at >= now,
                    Task.due_at <= soon_threshold,
                    (
                        Task.assignee_id == access.user.id
                        if _worker_like_role(access.user.role.value)
                        else True
                    ),
                )
            )
        ).scalar_one()
        or 0
    )

    overdue_deadline_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ComplianceDeadline)
                .where(
                    ComplianceDeadline.tenant_id == tenant.id,
                    or_(
                        ComplianceDeadline.status == "overdue",
                        and_(ComplianceDeadline.status == "due", ComplianceDeadline.due_at < now),
                    ),
                )
            )
        ).scalar_one()
        or 0
    )

    pending_sync = int(
        (
            await session.execute(
                select(func.count())
                .select_from(OfflineSyncBatch)
                .where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "pending",
                )
            )
        ).scalar_one()
        or 0
    )
    failed_sync = int(
        (
            await session.execute(
                select(func.count())
                .select_from(OfflineSyncBatch)
                .where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "failed",
                )
            )
        ).scalar_one()
        or 0
    )

    candidate_tasks = (
        (
            await session.execute(
                task_stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(
                    limit
                )
            )
        )
        .scalars()
        .all()
    )

    blockers = await _readiness_blockers(session=session, tenant=tenant, now=now)

    # Дисциплины (BIZ-54-57 срез-1, разд. 57.2). Рабочей роли показываем ТОЛЬКО
    # её собственные записи: у медосмотров и выдач СИЗ поимённый учёт, и чужая
    # строка на экране — это утечка персональных данных, а не косметика.
    # Связи User→Person в моделях нет, она ищется по e-mail; нет совпадения —
    # персональных записей нет, и подмешивать общий список НЕЛЬЗЯ.
    role = access.user.role.value
    # Чужие записи видят ТОЛЬКО роли, которым они и так открыты на профильных
    # экранах. Остальным (сотрудник, ученик, бухгалтер, инспектор подрядчика,
    # админ клиента…) подмешиваются лишь их собственные, найденные по e-mail;
    # нет кадровой записи — не подмешиваем ничего. Роль с привязкой к компании
    # тоже идёт по личной ветке: агрегатор не умеет сужать по компании, и в
    # арендаторе-аутсорсере админ одного клиента увидел бы записи другого.
    tenant_wide = role in _DISCIPLINE_TENANT_WIDE_ROLES and not getattr(
        access, "company_id", None
    )
    facts = _DisciplineFacts([], {}, shown=0)
    person_id: str | None = None
    if not tenant_wide:
        person_id = await resolve_person_id(
            session, tenant.id, getattr(access.user, "email", None)
        )
    if tenant_wide or person_id:
        facts = await _discipline_events(
            session=session,
            tenant=tenant,
            person_id=person_id,
            now=now,
            limit=limit,
        )
    discipline_events = facts.events

    items: list[AttentionItem] = []
    for task in candidate_tasks:
        due_at = task.due_at.astimezone(timezone.utc) if task.due_at else None
        if due_at and due_at < now:
            severity = "critical"
            reason = "Задача просрочена"
        elif due_at and due_at <= soon_threshold:
            severity = "high"
            reason = "Срок задачи скоро"
        else:
            severity = "medium"
            reason = "Открытая задача"
        items.append(
            AttentionItem(
                item_type="task",
                id=task.id,
                severity=severity,
                title=task.title,
                status=task.status.value,
                due_at=task.due_at,
                entity_type=task.entity_type,
                entity_id=task.entity_id,
                reason=reason,
            )
        )

    # Записи дисциплин идут в тот же список, что задачи: у специалиста один
    # вопрос «что горит», а не два по разным вкладкам.
    # Просрочки — из честных COUNT'ов агрегатора; «скоро срок» считается по
    # показанному списку и потому помечается ``truncated``, когда показано не
    # всё: занизить молча хуже, чем сказать «показаны не все».
    counts: dict[Discipline, dict[str, int]] = {
        code: {"overdue": facts.overdue.get(code, 0), "due_soon": 0}
        for code in MEASURED_DISCIPLINES
    }
    for event in discipline_events:
        discipline = discipline_of(event.source_type)
        overdue = event.is_overdue
        if discipline is not None and not overdue:
            counts.setdefault(discipline, {"overdue": 0, "due_soon": 0})
            counts[discipline]["due_soon"] += 1
        items.append(
            AttentionItem(
                item_type=event.source_type,
                id=event.id,
                severity="critical" if overdue else "high",
                title=event.title,
                status=event.status or ("overdue" if overdue else "due_soon"),
                due_at=event.starts_at,
                entity_type=event.source_type,
                entity_id=event.source_id,
                reason="Срок прошёл" if overdue else "Срок подходит",
                discipline=discipline.value if discipline else None,
            )
        )

    disciplines = [
        DisciplineAttention(
            code=code.value,
            title=DISCIPLINE_TITLES[code],
            measured=code in MEASURED_DISCIPLINES,
            overdue=counts.get(code, {}).get("overdue", 0),
            due_soon=counts.get(code, {}).get("due_soon", 0),
            reason=UNMEASURED_DISCIPLINES.get(code),
        )
        for code in Discipline
    ]
    items_truncated = facts.truncated

    recs: list[str] = []
    if overdue_task_total > 0:
        recs.append("Сначала закройте просроченные задачи")
    if overdue_deadline_total > 0:
        recs.append("Разберите просроченные обязательства соответствия")
    overdue_disciplines = [
        DISCIPLINE_TITLES[code] for code, nums in counts.items() if nums["overdue"] > 0
    ]
    if overdue_disciplines:
        recs.append("Просрочено по дисциплинам: " + ", ".join(overdue_disciplines))
    if failed_sync > 0:
        recs.append("Проверьте неудачные пакеты offline-синхронизации перед следующей выгрузкой")
    if blockers:
        recs.append("Устраните блокеры готовности перед запуском зависимых сценариев")
    if not recs:
        recs.append("Критичных блокеров не обнаружено — продолжайте плановую работу")

    return WorkspaceAttentionResponse(
        generated_at=now,
        summary=AttentionSummary(
            overdue_tasks=overdue_task_total,
            due_soon_tasks=due_soon_task_total,
            overdue_deadlines=overdue_deadline_total,
            pending_sync_batches=pending_sync,
            failed_sync_batches=failed_sync,
            readiness_blockers=len(blockers),
        ),
        items=items,
        blockers=blockers,
        recommendations=recs,
        disciplines=disciplines,
        items_truncated=items_truncated,
        unclassified_sources=[
            f"{DISCIPLINE_TITLES.get(discipline_of(source), source)}: {reason}"
            if discipline_of(source)
            else reason
            for source, reason in UNCLASSIFIED_SOURCES.items()
        ],
    )


@router.get("/task-inbox", response_model=WorkspaceTaskInboxResponse)
async def workspace_task_inbox(
    tenant: TenantDep,
    session: SessionDep,
    access: AccessDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WorkspaceTaskInboxResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    now = datetime.now(timezone.utc)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]
    stmt = select(Task).where(Task.tenant_id == tenant.id, Task.status.in_(open_statuses))
    if _worker_like_role(access.user.role.value):
        stmt = stmt.where(Task.assignee_id == access.user.id)

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0
    )
    rows = (
        (
            await session.execute(
                stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    items: list[TaskInboxItem] = []
    for item in rows:
        due_utc = _as_utc(item.due_at)
        items.append(
            TaskInboxItem(
                id=item.id,
                title=item.title,
                status=item.status.value,
                priority=item.priority.value,
                due_at=item.due_at,
                assignee_id=item.assignee_id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                overdue=bool(due_utc and due_utc < now),
            )
        )
    overdue_count = sum(1 for item in items if item.overdue)
    return WorkspaceTaskInboxResponse(total=total, overdue=overdue_count, items=items)


# ---------------------------------------------------------------------------
# OPS-002: Role-specific Workspace Projections  GET /workspace/role-summary
# ---------------------------------------------------------------------------

_SAFETY_ROLES = {"safety_lead", "safety_manager", "admin", "owner"}
_HR_ROLES = {"hr", "hr_manager", "admin", "owner"}
_MANAGER_ROLES = {"line_manager", "manager", "admin", "owner"}


class RoleWorkspaceSummary(BaseModel):
    generated_at: datetime
    role: str
    open_tasks: int
    overdue_tasks: int
    open_incidents: int
    open_inspections: int
    overdue_training: int
    expired_ppe: int
    overdue_deadlines: int
    recommendations: list[str] = Field(default_factory=list)


@router.get("/role-summary", response_model=RoleWorkspaceSummary)
async def role_workspace_summary(
    tenant: TenantDep,
    session: SessionDep,
    access: AccessDep,
) -> RoleWorkspaceSummary:
    """Role-specific aggregated workspace summary for safety leads, HR, managers and executives."""
    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(timezone.utc)
    role = access.user.role.value if hasattr(access.user.role, "value") else str(access.user.role)
    open_statuses_task = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]

    task_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == tenant.id,
            Task.status.in_(open_statuses_task),
        )
    )
    overdue_task_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == tenant.id,
            Task.status.in_(open_statuses_task),
            Task.due_at.is_not(None),
            Task.due_at < now,
        )
    )
    # Scope by role
    if role in _MANAGER_ROLES and role not in _SAFETY_ROLES and role not in _HR_ROLES:
        task_stmt = task_stmt.where(Task.assignee_id == access.user.id)
        overdue_task_stmt = overdue_task_stmt.where(Task.assignee_id == access.user.id)

    open_tasks = int((await session.execute(task_stmt)).scalar_one() or 0)
    overdue_tasks = int((await session.execute(overdue_task_stmt)).scalar_one() or 0)

    # Incidents (open/investigating) — relevant for safety roles
    open_incidents = 0
    if role in _SAFETY_ROLES:
        open_incidents = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Incident)
                    .where(
                        Incident.tenant_id == tenant.id,
                        Incident.deleted_at.is_(None),
                        Incident.status.in_(
                            [IncidentStatus.REPORTED, IncidentStatus.INVESTIGATING]
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )

    # Inspections (open/scheduled) — safety roles
    open_inspections = 0
    if role in _SAFETY_ROLES:
        open_inspections = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Inspection)
                    .where(
                        Inspection.tenant_id == tenant.id,
                        Inspection.deleted_at.is_(None),
                        Inspection.status.in_(
                            [InspectionStatus.PLANNED, InspectionStatus.IN_PROGRESS]
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )

    # Overdue training — HR roles
    overdue_training = 0
    if role in _HR_ROLES:
        overdue_training = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(TrainingEnrollment)
                    .where(
                        TrainingEnrollment.tenant_id == tenant.id,
                        TrainingEnrollment.deleted_at.is_(None),
                        TrainingEnrollment.status.in_(["assigned", "in_progress"]),
                        TrainingEnrollment.due_at.is_not(None),
                        TrainingEnrollment.due_at < now,
                    )
                )
            ).scalar_one()
            or 0
        )

    # Expired issued PPE — safety / HR
    expired_ppe = 0
    if role in _SAFETY_ROLES | _HR_ROLES:
        expired_ppe = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PPEIssue)
                    .where(
                        PPEIssue.tenant_id == tenant.id,
                        PPEIssue.deleted_at.is_(None),
                        PPEIssue.status == PPEIssueStatus.ISSUED,
                        PPEIssue.expires_at.is_not(None),
                        PPEIssue.expires_at < now,
                    )
                )
            ).scalar_one()
            or 0
        )

    # Overdue compliance deadlines
    overdue_deadlines = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ComplianceDeadline)
                .where(
                    ComplianceDeadline.tenant_id == tenant.id,
                    or_(
                        ComplianceDeadline.status == "overdue",
                        and_(ComplianceDeadline.status == "due", ComplianceDeadline.due_at < now),
                    ),
                )
            )
        ).scalar_one()
        or 0
    )

    recs: list[str] = []
    if overdue_tasks > 0:
        recs.append(f"Close {overdue_tasks} overdue task(s)")
    if open_incidents > 0:
        recs.append(f"Investigate {open_incidents} open incident(s)")
    if overdue_training > 0:
        recs.append(f"Resolve {overdue_training} overdue training assignment(s)")
    if expired_ppe > 0:
        recs.append(f"Issue replacement for {expired_ppe} expired PPE item(s)")
    if overdue_deadlines > 0:
        recs.append(f"Address {overdue_deadlines} overdue compliance deadline(s)")
    if not recs:
        recs.append("All operational indicators are within normal range")

    return RoleWorkspaceSummary(
        generated_at=now,
        role=role,
        open_tasks=open_tasks,
        overdue_tasks=overdue_tasks,
        open_incidents=open_incidents,
        open_inspections=open_inspections,
        overdue_training=overdue_training,
        expired_ppe=expired_ppe,
        overdue_deadlines=overdue_deadlines,
        recommendations=recs,
    )


# ---------------------------------------------------------------------------
# PHASE 1.1: Role-Based Workspaces - User Workspace Config
# ---------------------------------------------------------------------------


class WorkspaceConfig(BaseModel):
    """Role-specific workspace configuration for authenticated user."""

    role: str
    workspace_type: str
    primary_modules: list[str] = Field(default_factory=list)
    dashboard_route: str
    kpis_enabled: list[str] = Field(default_factory=list)
    quick_actions: list[dict[str, str]] = Field(default_factory=list)


_ROLE_WORKSPACE_MAPPING: dict[str, dict[str, object]] = {
    # OT/Safety roles
    "owner": {
        "workspace_type": "executive",
        "dashboard_route": "/dashboard",
        "primary_modules": [
            "dashboard",
            "risk",
            "incidents",
            "inspections",
            "training",
            "ppe",
            "documents",
        ],
        "kpis_enabled": [
            "overdue_tasks",
            "critical_obligations",
            "incidents_open",
            "training_status",
        ],
        "quick_actions": [
            {"label": "Create Document", "route": "/documents/wizard"},
            {"label": "View Tasks", "route": "/tasks"},
            {"label": "Run Master", "route": "/packs"},
        ],
    },
    "admin": {
        "workspace_type": "admin",
        "dashboard_route": "/dashboard",
        "primary_modules": [
            "dashboard",
            "admin",
            "rbac_abac",
            "tenancy",
            "risk",
            "incidents",
            "documents",
        ],
        "kpis_enabled": [
            "overdue_tasks",
            "critical_obligations",
            "incidents_open",
            "readiness_blockers",
        ],
        "quick_actions": [
            {"label": "Manage Users", "route": "/admin/users"},
            {"label": "View Tasks", "route": "/tasks"},
            {"label": "System Health", "route": "/admin"},
        ],
    },
    "ot_pb_lead": {
        "workspace_type": "safety_lead",
        "dashboard_route": "/dashboard",
        "primary_modules": [
            "dashboard",
            "risk",
            "incidents",
            "inspections",
            "ppe",
            "documents",
            "tasks",
        ],
        "kpis_enabled": ["overdue_tasks", "open_incidents", "open_inspections", "expired_ppe"],
        "quick_actions": [
            {"label": "New Incident", "route": "/incidents"},
            {"label": "Schedule Inspection", "route": "/inspections"},
            {"label": "My Tasks", "route": "/tasks?assigned=me"},
        ],
    },
    "ot_specialist": {
        "workspace_type": "specialist",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "risk", "ppe", "incidents", "documents", "tasks"],
        "kpis_enabled": ["overdue_tasks", "expired_ppe"],
        "quick_actions": [
            {"label": "Check PPE", "route": "/ppe"},
            {"label": "My Tasks", "route": "/tasks?assigned=me"},
            {"label": "View Risks", "route": "/risks"},
        ],
    },
    "hr": {
        "workspace_type": "hr",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "training", "medical", "persons", "documents", "tasks"],
        "kpis_enabled": ["overdue_training", "overdue_tasks"],
        "quick_actions": [
            {"label": "Assign Training", "route": "/training"},
            {"label": "Register Medical", "route": "/medical"},
            {"label": "Manage Employees", "route": "/persons"},
        ],
    },
    "teacher": {
        "workspace_type": "trainer",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "training", "briefings", "documents"],
        "kpis_enabled": ["overdue_training"],
        "quick_actions": [
            {"label": "My Assignments", "route": "/training?teacher=me"},
            {"label": "Create Briefing", "route": "/briefings"},
        ],
    },
    "student": {
        "workspace_type": "learner",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "training", "documents"],
        "kpis_enabled": [],
        "quick_actions": [
            {"label": "My Training", "route": "/training?student=me"},
            {"label": "My Documents", "route": "/documents?owner=me"},
        ],
    },
    "manager": {
        "workspace_type": "manager",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "tasks", "team", "documents", "incidents"],
        "kpis_enabled": ["overdue_tasks", "team_performance"],
        "quick_actions": [
            {"label": "Team Tasks", "route": "/tasks?team=me"},
            {"label": "View Team", "route": "/team"},
        ],
    },
    "worker": {
        "workspace_type": "operator",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "tasks", "documents"],
        "kpis_enabled": [],
        "quick_actions": [
            {"label": "My Tasks", "route": "/tasks?assigned=me"},
            {"label": "My Documents", "route": "/documents?owner=me"},
        ],
    },
    "auditor_ro": {
        "workspace_type": "auditor",
        "dashboard_route": "/dashboard",
        "primary_modules": ["dashboard", "audit", "documents", "risks", "incidents"],
        "kpis_enabled": ["open_incidents", "high_risks"],
        "quick_actions": [
            {"label": "View Audit Log", "route": "/audit"},
            {"label": "Compliance Check", "route": "/compliance"},
        ],
    },
}


@router.get("/users/me/workspace", response_model=WorkspaceConfig)
async def get_user_workspace_config(
    tenant: TenantDep,
    access: AccessDep,
) -> WorkspaceConfig:
    """Get role-specific workspace configuration for the authenticated user.

    Returns workspace layout, primary modules, enabled KPIs, and quick actions
    based on the user's role.
    """
    TenantContextValidator.ensure_tenant_context(tenant)

    role = access.user.role.value if hasattr(access.user.role, "value") else str(access.user.role)

    # Get role-specific configuration or use sensible defaults
    config = _ROLE_WORKSPACE_MAPPING.get(role)
    if config is None:
        # Default fallback for unmapped roles
        config = {
            "workspace_type": "standard",
            "dashboard_route": "/dashboard",
            "primary_modules": ["dashboard", "documents", "tasks"],
            "kpis_enabled": ["overdue_tasks"],
            "quick_actions": [
                {"label": "View Tasks", "route": "/tasks"},
                {"label": "View Documents", "route": "/documents"},
            ],
        }

    return WorkspaceConfig(
        role=role,
        workspace_type=str(config.get("workspace_type", "standard")),
        primary_modules=list(config.get("primary_modules", [])),
        dashboard_route=str(config.get("dashboard_route", "/dashboard")),
        kpis_enabled=list(config.get("kpis_enabled", [])),
        quick_actions=list(config.get("quick_actions", [])),
    )
