"""Pydantic-схемы ведомых клиентов (BIZ-49 срез-1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field, field_validator

from app.domains.managed_clients.attention import AggregationStatus, Severity, SignalKind
from app.domains.managed_clients.calendar import DeadlineKind
from app.domains.managed_clients.change_feed import ChangeStatus, ClientChangeKind
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.domains.managed_clients.workload import OverloadReason
from app.schemas.base import BaseSchema


def _strip_required(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Название клиента не может быть пустым")
    return cleaned


class ManagedClientCreate(BaseSchema):
    name: str = Field(max_length=255)
    mode: ManagedClientMode
    company_id: str | None = None
    dedicated_tenant_slug: str | None = Field(default=None, max_length=64)
    contract_no: str | None = Field(default=None, max_length=128)
    contract_starts_at: date | None = None
    contract_ends_at: date | None = None
    responsible_person_id: str | None = None
    notes: str | None = None
    #: Куда слать отчёт о состоянии соответствия (BIZ-51 срез-11, разд. 51.3).
    report_email: str | None = Field(default=None, max_length=320)
    #: Согласие клиента на рассылку. Адрес без согласия — не основание писать,
    #: поэтому поля два, а не одно.
    report_opt_in: bool = False

    _name_not_blank = field_validator("name")(_strip_required)


class ManagedClientUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    mode: ManagedClientMode | None = None
    company_id: str | None = None
    dedicated_tenant_slug: str | None = Field(default=None, max_length=64)
    contract_status: ContractStatus | None = None
    contract_no: str | None = Field(default=None, max_length=128)
    contract_starts_at: date | None = None
    contract_ends_at: date | None = None
    responsible_person_id: str | None = None
    notes: str | None = None
    report_email: str | None = Field(default=None, max_length=320)
    report_opt_in: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _strip_required(value)


class ManagedClientRead(BaseSchema):
    id: str
    name: str
    mode: ManagedClientMode
    company_id: str | None
    dedicated_tenant_slug: str | None
    contract_status: ContractStatus
    contract_no: str | None
    contract_starts_at: date | None
    contract_ends_at: date | None
    responsible_person_id: str | None
    notes: str | None
    #: Адрес и согласие на отчёт (BIZ-51 срез-11). Показываются в карточке,
    #: чтобы специалист видел, можно ли вообще отправлять.
    report_email: str | None = None
    report_opt_in: bool = False
    created_at: datetime
    updated_at: datetime


class PortfolioItem(ManagedClientRead):
    """Строка портфеля: карточка клиента + вычисленные сигналы (разд. 49.2)."""

    contract_days_left: int | None = None
    contract_expiring: bool = False


class PortfolioSummary(BaseSchema):
    total: int = 0
    active: int = 0
    draft: int = 0
    suspended: int = 0
    terminated: int = 0
    lightweight: int = 0
    dedicated: int = 0
    contracts_expiring: int = 0


class PortfolioPage(BaseSchema):
    items: list[PortfolioItem]
    summary: PortfolioSummary
    total: int
    limit: int
    offset: int


# --- Cross-client attention (срез-2, разд. 49.2) ---
class AttentionSignalRead(BaseSchema):
    kind: SignalKind
    count: int
    severity: Severity
    title: str
    action_hint: str


class ClientAttentionRead(BaseSchema):
    client_id: str
    client_name: str
    aggregation: AggregationStatus
    signals: list[AttentionSignalRead]
    #: ``None`` = данные клиента в этом срезе не собирались (свой контур).
    total: int | None = None
    severity: Severity | None = None
    reason: str | None = None


class CrossClientAttentionSummary(BaseSchema):
    clients_total: int = 0
    clients_with_signals: int = 0
    clients_not_aggregated: int = 0
    signals_total: int = 0
    critical_clients: int = 0


class CrossClientAttentionResponse(BaseSchema):
    generated_at: datetime
    summary: CrossClientAttentionSummary
    items: list[ClientAttentionRead]


# --- Cross-client календарь (срез-4, разд. 49.2) ---
class DeadlineEventRead(BaseSchema):
    kind: DeadlineKind
    title: str
    due_date: date
    client_id: str
    client_name: str
    subject: str
    responsible_person_id: str | None = None
    days_left: int
    overdue: bool


class DeadlineDayRead(BaseSchema):
    due_date: date
    overdue: bool
    events: list[DeadlineEventRead]


class CalendarSummary(BaseSchema):
    events_total: int = 0
    overdue: int = 0
    due_today: int = 0
    upcoming: int = 0
    clients_touched: int = 0


class CrossClientCalendarResponse(BaseSchema):
    generated_at: datetime
    horizon_days: int
    summary: CalendarSummary
    days: list[DeadlineDayRead]


# --- Загрузка специалистов (срез-5, разд. 49.2) ---
class OverloadReasonRead(BaseSchema):
    code: OverloadReason
    text: str


class SpecialistWorkloadRead(BaseSchema):
    person_id: str
    person_name: str | None = None
    #: Строка «клиенты без ответственного» — не специалист, но и не невидимка.
    unassigned: bool
    clients_total: int
    clients_critical: int
    signals_total: int
    overdue_deadlines: int
    overloaded: bool
    overload_reasons: list[OverloadReasonRead]


class WorkloadThresholdsRead(BaseSchema):
    """Пороги в ответе: руководитель должен видеть, по какому правилу красное."""

    max_clients: int
    max_signals: int
    max_overdue: int


class WorkloadSummary(BaseSchema):
    specialists_total: int = 0
    overloaded: int = 0
    clients_unassigned: int = 0


class SpecialistWorkloadResponse(BaseSchema):
    generated_at: datetime
    thresholds: WorkloadThresholdsRead
    summary: WorkloadSummary
    items: list[SpecialistWorkloadRead]


# --- Матрица доступа (срез-6, разд. 49.3) ---
class AccessGrantCreate(BaseSchema):
    user_id: str
    #: Доступ ко всему клиенту объявляется явно; пустой список — не «всё».
    all_modules: bool = False
    modules: list[str] = Field(default_factory=list)


class AccessGrantRead(BaseSchema):
    id: str
    managed_client_id: str
    user_id: str
    all_modules: bool
    modules: list[str]
    granted_by_user_id: str | None = None
    granted_at: datetime
    revoked_at: datetime | None = None
    revoked_by_user_id: str | None = None
    active: bool


class ConvertToDedicated(BaseSchema):
    """Перевод Lightweight → Dedicated (срез-13, разд. 49.1)."""

    tenant_slug: str
    #: Имя нового арендатора; по умолчанию — имя клиента.
    tenant_name: str | None = None
    owner_email: str
    owner_password: str


class ConversionRead(BaseSchema):
    """Итог перевода: клиент + что создано в новом арендаторе."""

    client: "ManagedClientRead"
    tenant_slug: str
    #: Сущности, созданные bootstrap'ом нового арендатора.
    tenant_created: list[str]
    #: Организация клиента остаётся в пространстве аутсорсера ссылкой на
    #: историю (инвариант режима из среза-1); перенос доменных данных —
    #: следующий срез 49.1.
    history_company_id: str | None = None


class TransferRead(BaseSchema):
    """Итог переноса данных клиента в его арендатор (срез-14, разд. 49.1)."""

    id: str
    managed_client_id: str
    target_tenant_slug: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    started_by_user_id: str | None = None
    #: {"company": 1, "people": N, "people_skipped": M} — обезличенные и
    #: удалённые не переносятся (разд. 66.2), это видно честной цифрой.
    counts: dict[str, int]


class ConsentCreate(BaseSchema):
    """Согласие клиента на делегированный доступ (срез-12, разд. 66.3)."""

    #: Реквизиты документа-основания — согласие «на словах» не основание.
    document_ref: str
    #: Срок из документа; истёкшее согласие равно отозванному.
    expires_at: datetime | None = None


class ConsentRevoke(BaseSchema):
    reason: str | None = None


class ConsentRead(BaseSchema):
    id: str
    managed_client_id: str
    document_ref: str
    granted_by_user_id: str | None = None
    granted_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: str | None = None
    revoke_reason: str | None = None
    active: bool


class MyManagedClient(BaseSchema):
    """Клиент, доступный текущему специалисту (основа переключателя, разд. 49.3)."""

    client_id: str
    client_name: str
    mode: ManagedClientMode
    all_modules: bool
    modules: list[str]


class MyManagedClientsResponse(BaseSchema):
    items: list[MyManagedClient]
    #: Разделы, где контекст клиента УЖЕ работает как фильтр (срез-9).
    #: Индикатор в интерфейсе называет именно их: обещать фильтр там, где его
    #: ещё нет, — это ровно тот случай, когда специалист верит вывеске и
    #: заводит документ не тому клиенту.
    scoped_sections: list[str] = []


# --- Контекст клиента (срез-7, разд. 49.3) ---
class ClientContextRead(BaseSchema):
    """Подтверждённый контекст: специалист работает от имени клиента."""

    client_id: str
    client_name: str
    mode: ManagedClientMode
    all_modules: bool
    modules: list[str]
    #: Подтверждение, что вход зафиксирован в аудите (требование ПДн из ТЗ).
    audit_recorded: bool = True
    #: Разделы, где контекст уже работает как фильтр (срез-9).
    scoped_sections: list[str] = []
    #: Когда работа «от имени» перестанет действовать (срез-10, Доп. №3 63.2).
    expires_at: datetime | None = None
    #: Сколько секунд осталось — чтобы интерфейс мог показать счётчик, а не
    #: вычислять срок сам и разъезжаться с сервером на часовых поясах.
    seconds_left: int | None = None


# --- Журнал доступа к данным клиента (срез-18, Доп. №3 разд. 63.2) ---
class ClientAccessLogEntry(BaseSchema):
    """Одно обращение специалиста к данным клиента «от имени» клиента."""

    at: datetime
    actor_user_id: str | None = None
    actor_email: str | None = None
    #: Метод и путь: чтение и правка — разные ответы на вопрос «кто трогал
    #: мои данные», и одним путём они не различаются.
    method: str | None = None
    path: str | None = None
    ip: str | None = None
    #: Идентификатор запроса — по нему в общем аудите видны сами изменения.
    correlation_id: str | None = None


class ClientAccessLogPage(BaseSchema):
    """Страница журнала: всегда с общим числом — «покажите всё» проверяемо."""

    items: list[ClientAccessLogEntry]
    total: int


class MyAccessLogPage(ClientAccessLogPage):
    """Тот же журнал, но в кабинете САМОГО клиента (SEC-63, разд. 63.2).

    Наследование, а не отдельная модель: это буквально те же записи, и разъехись
    поля — «кто трогал мои данные» начало бы отвечать разное в двух кабинетах.
    """

    #: Имя обслуживающей компании. `None` — арендатора никто не обслуживает;
    #: это обычное состояние, а не ошибка.
    served_by: str | None = None
    #: Строка для человека: пустой список без объяснения читается как поломка.
    summary: str


class ClientChangeCreate(BaseSchema):
    """Запись об изменении у клиента (BIZ-51 срез-1, разд. 51.1)."""

    kind: ClientChangeKind
    #: Дата САМОГО изменения, а не записи о нём: сотрудника приняли в пятницу,
    #: а внесли в понедельник — сроки считаются от пятницы.
    happened_on: date
    summary: str = Field(min_length=1, max_length=255)
    details: str | None = None


class ClientChangeRead(BaseSchema):
    id: str
    kind: ClientChangeKind
    #: Человеческое название вида: ленту читает специалист, а не машина.
    kind_title: str
    happened_on: date
    summary: str
    details: str | None = None
    status: ChangeStatus
    handled_at: datetime | None = None
    #: Что предложить по этому изменению (таблица разд. 51.1). Отдаётся вместе
    #: с записью: список «что теперь делать» и есть смысл ленты.
    suggestions: list[str]
    #: Откуда узнали (разд. 51.2): `manual` — внёс человек, `import` — увидели
    #: в загруженных данных. Проверяются такие записи по-разному, и без пометки
    #: вся лента выглядит внесённой руками.
    source: str = "manual"


class ClientChangePage(BaseSchema):
    items: list[ClientChangeRead]
    total: int
    #: Сводка словами: «требуют внимания N из M».
    summary: str


class ClientChangeStatusPatch(BaseSchema):
    """Разобрать изменение или отклонить его.

    `dismissed` существует намеренно: часть изменений не требует действий, и без
    «отклонить» лента копила бы вечные долги, а специалист перестал бы её
    открывать.
    """

    status: ChangeStatus


class DirectionReadinessRead(BaseSchema):
    """Одно направление светофора (BIZ-51 срез-5, разд. 51.3)."""

    direction: str
    title: str
    #: green / yellow / red / not_measured. Последнее — не цвет, а честное
    #: «эталона нет»: зелёный без эталона продавал бы тишину как благополучие.
    light: str
    #: Расшифровка обязательна: цвет без слов возвращает к гаданию.
    reason: str
    required: int
    missing: int
    lapsed: int
    expiring: int


class ClientReadinessRead(BaseSchema):
    """Светофор соответствия клиента: факт против эталона."""

    client_id: str
    client_name: str
    #: У Dedicated данные в другом арендаторе — честное not_aggregated,
    #: как в «Центре внимания», а не тихие нули.
    aggregation: str
    reason: str | None = None
    #: Итог по худшему ИЗМЕРЕННОМУ направлению; not_measured в итог не входит.
    overall: str | None = None
    directions: list[DirectionReadinessRead] = Field(default_factory=list)
    #: Дисциплины вне редакции исполнителя — одной фразой; null — скрывать нечего
    #: (BIZ-54-57 срез-55, приёмка §58.3).
    not_applicable: str | None = None


class ClientAuditReportRead(BaseSchema):
    """Отчёт авто-аудита (BIZ-51 срез-7, разд. 51.3): снимок на дату."""

    id: str
    period_start: date
    period_end: date
    #: Итог светофора на дату отчёта (green/yellow/red/not_measured).
    overall: str
    #: «Что изменилось, что просрочено, что нужно сделать» — одним текстом.
    summary: str
    #: Структура отчёта (направления, числа, действия).
    payload: dict[str, Any] = Field(default_factory=dict)


class ClientAuditReportPage(BaseSchema):
    items: list[ClientAuditReportRead]
    total: int


class AuditRunRead(BaseSchema):
    """Итог ручного прогона аудита — по слагаемым, без молчаливых потерь."""

    created: int
    #: Отчёт за эту дату уже есть — второй раз не пишем (динамика без шума).
    already_current: int
    #: Данные Dedicated-клиентов живут в их контурах — пропуск назван числом.
    skipped_dedicated: int
    summary: str


class ReportSendRead(BaseSchema):
    """Итог отправки отчёта клиенту (BIZ-51 срез-11, разд. 51.3).

    Причина обязательна: «не отправлено» одинаково выглядит и когда клиент не
    давал согласия, и когда на сервере не настроена почта, а чинят это разные
    люди.
    """

    status: str
    reason: str
    recipient: str | None = None


class DqSignalsRead(BaseSchema):
    """Итог сбора сигналов Data Quality (BIZ-51 срез-3, разд. 51.2).

    Каждая судьба находки — отдельным числом, и слагаемые сходятся с ``found``:
    «записано 3» без остального читалось бы как «просрочки три», хотя их
    тридцать (урок честного итога импорта).
    """

    #: Просрочек найдено проверками качества данных — всего по арендатору.
    found: int
    #: Записано в ленты клиентов этим сбором.
    recorded: int
    #: Уже были в лентах с прошлых сборов — не удваиваем.
    already_in_feed: int
    #: Не относятся к обслуживаемым клиентам (свои сотрудники и компании,
    #: которые аутсорсер не ведёт) — остаются в отчёте качества данных.
    not_client_related: int
    #: Находки без даты или без сотрудника — разобрать не из чего.
    unparsed: int
    #: Новые сверх потолка за один сбор: запишутся следующим.
    deferred: int
    truncated: bool
    #: Строка для человека: голые числа без объяснения читаются как поломка.
    summary: str
