"""Subscription plan catalogue — the source of truth for what each tier grants.

A *plan* bundles two things a paying tenant gets: a set of feature codes (which map
1:1 onto the ``feature`` flags every gated router already checks via
:func:`app.core.feature_flags.is_feature_enabled`) and a preset of quota limits.

There is deliberately **no** ``plan`` column in the database. Applying a plan writes
per-tenant ``FeatureEnablement`` rows and quota values; the tenant's *current* plan is
then derived back from its enabled feature set (:func:`plan_code_for_features`). Because
a plan is the only thing that rewrites the whole feature set at once, the derived code
always round-trips exactly — and a hand-tweaked tenant honestly reads back as "custom".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.subscription.registry import module_titles

__all__ = [
    "DEFAULT_PLAN_CODE",
    "FEATURE_CATALOG",
    "MODULE_EVENT_TYPES",
    "PLANS",
    "SubscriptionPlan",
    "plan_code_for_features",
]

# code -> human title. Every code here is a real gate: some router calls
# is_feature_enabled(<code>) and blocks (404) when the tenant lacks it.
#
# BIZ-61 срез-1: значения больше не набираются здесь руками — они выводятся из
# реестра модулей (``registry.py``), где у модуля есть ещё и категория, признак
# ядра, экраны фронтенда и права. Набор кодов при этом НЕ изменился: он
# участвует в сопоставлении тарифов, и лишняя строка сдвинула бы тариф у
# существующих арендаторов. Модули ядра в каталог не попадают по построению.
FEATURE_CATALOG: dict[str, str] = module_titles()

# SEC-63 (разд. 63.3), риск «осиротевшие доступы»: типы событий, которые порождает
# ТОЛЬКО данный модуль (по фактическим точкам испускания, не по названию). При
# отключении модуля apply_plan убирает эти типы из вебхук-подписок арендатора и
# гасит опустевшие эндпоинты (services/tenants/subscription.py). Правила ведения:
#
# * каждый код каталога обязан иметь запись — хотя бы пустую (полноту держит
#   tests/test_module_event_prune.py, значения сверяются с EventType);
# * событие может числиться максимум за ОДНИМ модулем; сквозные события ядра
#   (DocumentGenerated, PPEIssued, TrainingCompleted, …) сюда не входят — их
#   порождает и базовый контур, отключение модуля не должно рвать их доставку;
# * PPEWrittenOff/PPEReplacementDue НЕ у warehouse: их испускает базовый цикл
#   выдачи СИЗ (routes/ppe.py::writeoff, services/ppe_notifications.py), склад
#   лишь списывает остатки.
MODULE_EVENT_TYPES: dict[str, frozenset[str]] = {
    # BIZ-49 срез-1 — портфель клиентов событий пока не испускает.
    "managed_clients": frozenset(),
    "committees": frozenset(),
    "contractors": frozenset(
        {
            "contractor.readiness_blocked",
            "contractor.readiness_warning",
            "contractor.document_expiring",
            "contractor.document_expired",
        }
    ),
    "medical": frozenset({"MedicalExamRecorded", "PersonSuspended", "PersonReinstated"}),
    "report_builder": frozenset(),
    "budget": frozenset(),
    "sout": frozenset(),
    "rules_engine": frozenset({"rule.triggered"}),
    # BIZ-54-57 срез-2: сводки ПБ строятся из общих данных и своих событий не
    # испускают — пустая запись обязательна, её требует страж полноты.
    "fire_safety": frozenset(),
    # Доп. №1 разд. 54.2 срез-1: реестр ОПО своих событий не испускает —
    # пустая запись обязательна, её требует страж полноты. Единственное
    # событие, размеченное ПромБезом, — WorkPermitIssued с газоопасными
    # работами, но испускает его контур нарядов-допусков (ядро), и гасить его
    # вместе с модулем нельзя: наряды продаются не этим модулем.
    "industrial_safety": frozenset(),
    # Доп. №1 разд. 55 срез-1: реестр объектов НВОС своих событий не испускает —
    # пустая запись обязательна, её требует страж полноты. Без неё смена
    # тарифа падает с KeyError у ВСЕХ арендаторов (урок среза ПромБеза).
    "ecology": frozenset(),
    # Доп. №1 разд. 56.1 срез-1: реестр формирований ГО-ЧС своих событий не
    # испускает — пустая запись обязательна по тому же правилу.
    "civil_defense": frozenset(),
    "warehouse": frozenset(),
}


@dataclass(frozen=True)
class SubscriptionPlan:
    """One subscription tier: which features it unlocks and its quota preset."""

    code: str
    title: str
    features: frozenset[str]
    quotas: dict[str, int] = field(default_factory=dict)


# Tiers grow strictly: each higher plan is a superset of the lower one's features,
# so "upgrade" only ever adds. Quota presets scale with the tier.
PLANS: dict[str, SubscriptionPlan] = {
    "free": SubscriptionPlan(
        code="free",
        title="Базовый",
        features=frozenset({"committees", "contractors", "medical"}),
        quotas={
            "max_doc_generations_per_month": 500,
            "max_storage_mb": 5120,
            "max_parallel_jobs": 2,
        },
    ),
    "pro": SubscriptionPlan(
        code="pro",
        title="Про",
        features=frozenset(
            {"committees", "contractors", "medical", "report_builder", "budget", "sout"}
        ),
        quotas={
            "max_doc_generations_per_month": 5000,
            "max_storage_mb": 20480,
            "max_parallel_jobs": 4,
        },
    ),
    "enterprise": SubscriptionPlan(
        code="enterprise",
        title="Всё включено",
        features=frozenset(FEATURE_CATALOG),
        quotas={
            "max_doc_generations_per_month": 50000,
            "max_storage_mb": 102400,
            "max_parallel_jobs": 8,
        },
    ),
}

DEFAULT_PLAN_CODE = "free"


def plan_code_for_features(enabled: set[str]) -> str | None:
    """Return the plan whose feature set is exactly ``enabled``, else ``None``.

    Only codes in :data:`FEATURE_CATALOG` are considered, so stray flags outside the
    catalogue never break the match. ``None`` means "custom" — no tier matches.
    """

    catalogued = enabled & set(FEATURE_CATALOG)
    for plan in PLANS.values():
        if set(plan.features) == catalogued:
            return plan.code
    return None
