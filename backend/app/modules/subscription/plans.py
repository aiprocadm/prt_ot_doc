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

__all__ = [
    "DEFAULT_PLAN_CODE",
    "FEATURE_CATALOG",
    "PLANS",
    "SubscriptionPlan",
    "plan_code_for_features",
]

# code -> human title. Every code here is a real gate: some router calls
# is_feature_enabled(<code>) and blocks (404) when the tenant lacks it. Keep this
# list in sync with the _FEATURE_CODE constants across the gated routers.
FEATURE_CATALOG: dict[str, str] = {
    "committees": "Комитеты",
    "contractors": "Подрядчики",
    "medical": "Медосмотры",
    "report_builder": "Конструктор отчётов",
    "budget": "Бюджет безопасности",
    "sout": "СОУТ",
    "rules_engine": "Правила автоматизации",
    "warehouse": "Склад СИЗ",
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
