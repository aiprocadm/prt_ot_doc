from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema

#: Вид арендатора. Это его УРОВЕНЬ в иерархии продажи платформы (Доп. №1
#: разд. 52.1), а не ярлык: ``reseller`` — партнёр, который ведёт своих клиентов,
#: остальные значения — клиентские. Объявлен один раз, потому что раньше тот же
#: список был выписан в трёх схемах и разъехался бы при первом же добавлении.
TenantKind = Literal["customer", "branch", "contractor", "reseller"]


class TenantQuotaRead(BaseSchema):
    tenant_id: str
    max_parallel_jobs: int
    max_doc_generations_per_month: int
    max_storage_mb: int
    monthly_edo_outgoing: int
    enforce_billing_gate: bool


class TenantRead(BaseSchema):
    id: str
    name: str
    slug: str
    code: str | None = None
    contact_email: str
    is_active: bool
    parent_id: str | None = None
    kind: TenantKind | None = None
    schema_name: str | None = None


class TenantPage(BaseSchema):
    items: list[TenantRead]
    total: int


class TenantCreate(BaseSchema):
    slug: str
    name: str
    contact_email: str
    code: str | None = None
    # Запрошенный родитель — ПОЖЕЛАНИЕ, а не команда: что именно запишется,
    # решают правила иерархии (`domains/reseller/hierarchy.py`). Реселлеру своё
    # значение подставят принудительно, клиенту создавать вообще нельзя.
    parent_id: str | None = None
    kind: TenantKind = "customer"


class TenantQuotaPatch(BaseSchema):
    max_parallel_jobs: int | None = Field(default=None, ge=1)
    max_doc_generations_per_month: int | None = Field(default=None, ge=1)
    max_storage_mb: int | None = Field(default=None, ge=1)
    monthly_edo_outgoing: int | None = Field(default=None, ge=0)
    enforce_billing_gate: bool | None = None


# The slug becomes a Postgres schema name (``tenant_<slug>``), so it is restricted to a
# safe identifier alphabet instead of the free-form string ``TenantCreate`` accepts.
TENANT_SLUG_PATTERN = r"^[a-z][a-z0-9_-]{1,30}$"


class TenantProvisionRequest(BaseSchema):
    slug: str = Field(pattern=TENANT_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=128)
    kind: TenantKind = "customer"
    parent_id: str | None = None
    demo_data: bool = False
    #: Отрасль клиента (BIZ-52 срез-12, разд. 52.3): от неё зависит, какие
    #: должности, опасности и меры получит новый арендатор. Пусто — общий
    #: набор, как было до появления отраслей. Список закрыт в
    #: `app.domains.reseller.industries`; неизвестный код — отказ, а не тихий
    #: откат на общий набор.
    industry: str | None = None


class TenantProvisionResult(BaseSchema):
    tenant: TenantRead
    created: list[str] = Field(default_factory=list)
    reused: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TenantStatusPatch(BaseSchema):
    is_active: bool


class TenantStatusResult(TenantRead):
    """Итог смены статуса — вместе с КАСКАДОМ (SEC-63.1, четвёртая угроза).

    Раньше ручка возвращала только строку арендатора, и оператор не узнавал,
    что вместе с партнёром в режим чтения ушли его клиенты. Для угрозы
    «каскадное отключение как оружие» это и есть недостающая мера: последствие
    должно быть видно тому, кто нажимает.

    **Наследует `TenantRead`, а не вкладывает его.** Вложение переставило бы
    `is_active` на уровень ниже — это слом контракта: и фронт (`tenantsApi.
    setStatus` ждёт `TenantDto`), и контрактный гейт OPS-73 читают поля сверху.
    Добавление полей рядом — аддитив, снятие или перенос — нет.
    """

    #: Слаги клиентов, сменивших режим работы. Пустой список у партнёра без
    #: клиентов — это факт, а не отсутствие данных (см. `cascade_summary`).
    cascade_affected: list[str] = Field(default_factory=list)
    #: Человеческая формулировка: «каскада нет» и «каскад пуст» — разные вещи.
    cascade_summary: str = ""


class TenantCascadePreview(BaseSchema):
    """Кого затронет смена статуса — ДО того, как её сделали.

    Приставка `Tenant` в имени намеренно: короткое `CascadePreview` уже занято
    модулем СОУТ, и совпадение заставило FastAPI переименовать ОБЕ схемы в
    `app__schemas__*__CascadePreview` — прежнее имя исчезло бы из контракта и
    сломало всех, кто на него ссылается. Поймано контрактным гейтом OPS-73.
    """

    tenant_id: str
    slug: str
    is_reseller: bool
    cascade_affected: list[str] = Field(default_factory=list)
    cascade_summary: str = ""


class TenantFeatureRead(BaseSchema):
    code: str
    title: str
    on: bool
    #: Дата окончания пробного доступа (BIZ-61 срез-3, разд. 61.2).
    #: ``None`` — выдано бессрочно либо не выдано вовсе. Консоли этого поля
    #: недостаточно знать по ``on``: «включено» и «включено до 22 августа» —
    #: разные ответы клиенту.
    trial_until: datetime | None = None


class TenantFleetItem(BaseSchema):
    tenant: TenantRead
    quotas: TenantQuotaRead | None = None
    # ``plan`` is derived from the enabled feature set: a known tier code, or ``None``
    # for a hand-tweaked ("custom") tenant / one that never had a plan applied.
    plan: str | None = None
    features: list[TenantFeatureRead] = Field(default_factory=list)


class TenantFleetPage(BaseSchema):
    items: list[TenantFleetItem]
    total: int
    managing_tenant_slug: str
    #: Уровень СМОТРЯЩЕГО (BIZ-52 срез-2): владелец платформы или партнёр.
    #: Нужен интерфейсу для формулировок — «весь флот» и «мои клиенты» это
    #: разные экраны при одном наборе данных.
    viewer_level: Literal["platform", "reseller"] = "platform"
    #: Можно ли смотрящему менять тариф, квоты и пробный доступ. Флаг приходит
    #: С СЕРВЕРА, а не выводится на фронте: вычисли его во второй раз — и
    #: получишь вторую правду о правах, которая однажды разойдётся с первой.
    can_manage_commercials: bool = True


class TenantUsageRow(BaseSchema):
    """Расход одного арендатора за месяц (BIZ-52 срез-8, разд. 52.4).

    Срез-13 добавил остальные метрики ТЗ. Имя `doc_generations` сохранено:
    переименование сломало бы кабинет, который его уже читает.
    """

    tenant_id: str
    slug: str
    name: str
    doc_generations: int
    #: Занятое хранилище. Не «за период», а состояние: место занято, пока файлы
    #: лежат, и складывать такие значения по месяцам бессмысленно.
    storage_bytes: int = 0
    #: Активные сотрудники — тоже состояние, а не поток. Пересчитывается
    #: фоновой задачей `billing.recompute_active_workers`.
    active_workers: int = 0


class FleetUsageReport(BaseSchema):
    """Потребление по области кабинета.

    Итог считается по ТЕМ ЖЕ строкам, что вернулись: партнёр не должен видеть в
    итоге оборот чужих клиентов, которых нет в его списке.
    """

    period: str
    items: list[TenantUsageRow]
    total_doc_generations: int
    total_storage_bytes: int = 0
    #: Сумма активных сотрудников по клиентам области. Складывается честно:
    #: один человек не работает в двух арендаторах одновременно.
    total_active_workers: int = 0
    #: Метрики, которых в отчёте НЕТ, и почему. Пустой список — всё считается.
    #: Без этого поля отсутствие ЭДО в кабинете читалось бы как «ЭДО не
    #: пользуются», а правда — «мы это пока не считаем».
    not_measured: list[str] = Field(default_factory=list)


class OwnLimitLine(BaseSchema):
    """Строка «сколько можно и сколько занято» (BIZ-52 срез-15, разд. 52.4)."""

    code: str
    title: str
    unit: str
    #: `None` — предела нет.
    limit: int | None = None
    #: `None` — расход НЕ СЧИТАЕТСЯ. Это не то же, что ноль.
    used: int | None = None
    remaining: int | None = None
    exhausted: bool = False


class OwnLimitsReport(BaseSchema):
    """Свои лимиты и свой расход за период."""

    period: str
    tenant_slug: str
    items: list[OwnLimitLine]


class IndustryRead(BaseSchema):
    """Отрасль для выбора при заведении клиента (BIZ-52 срез-12, разд. 52.3)."""

    code: str
    title: str


class IndustryList(BaseSchema):
    items: list[IndustryRead]


class FeatureCatalogEntry(BaseSchema):
    code: str
    title: str


# --- BIZ-61 срез-1: реестр модулей (разд. 61.1) ------------------------------
class ModuleRegistryEntry(BaseSchema):
    """Модуль платформы со всеми атрибутами разд. 61.1."""

    code: str
    title: str
    #: Дисциплина или группа — по ней модуль ищут в консоли и в предложении.
    category: str
    #: ``True`` — ядро: выключить нельзя, в тарифы не входит.
    is_core: bool = False
    depends_on: list[str] = []
    #: Маршруты фронтенда модуля (разд. 61.3: скрыть навигацию выключенного).
    ui_routes: list[str] = []
    permissions: list[str] = []


class ModuleRegistryResponse(BaseSchema):
    modules: list[ModuleRegistryEntry]


# --- BIZ-61 срез-5: «мои модули» для фронтенда (разд. 61.3) ------------------
class MyModuleEntry(BaseSchema):
    """Модуль глазами текущего арендатора: включён или нет и какие экраны его."""

    code: str
    title: str
    category: str
    is_core: bool = False
    #: Выдан ли модуль ЭТОМУ арендатору сейчас (с учётом срока пробного доступа).
    enabled: bool
    #: Дата окончания пробного доступа, если модуль выдан на срок.
    trial_until: datetime | None = None
    #: Экраны модуля. Фронтенд прячет по ним навигацию и закрывает прямой переход
    #: по адресу — связь «модуль → экран» живёт на сервере, чтобы не разойтись.
    ui_routes: list[str] = []


class MyModulesResponse(BaseSchema):
    modules: list[MyModuleEntry]


class SubscriptionPlanRead(BaseSchema):
    code: str
    title: str
    feature_codes: list[str]
    quotas: dict[str, int] = Field(default_factory=dict)


class PlanCatalog(BaseSchema):
    plans: list[SubscriptionPlanRead]
    features: list[FeatureCatalogEntry]


class TenantPlanPatch(BaseSchema):
    plan: str


class ModuleTrialGrant(BaseSchema):
    """Выдать модуль на срок (разд. 61.2, «временный доступ на N дней»)."""

    days: int = Field(..., ge=1, le=180, description="Длительность пробного доступа в днях")


class ModuleTrialResult(BaseSchema):
    code: str
    title: str
    #: ``None`` в ответе на отзыв — доступа больше нет.
    trial_until: datetime | None = None
