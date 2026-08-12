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


class TenantProvisionResult(BaseSchema):
    tenant: TenantRead
    created: list[str] = Field(default_factory=list)
    reused: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TenantStatusPatch(BaseSchema):
    is_active: bool


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
