"""Сервис авто-каскада класса СОУТ → запись мед-норм (preview/apply).

Пишет ТОЛЬКО в существующую medical_norm (колонка working_conditions_class уже
есть) → миграции нет. apply повторно выводит план из БД (не доверяет клиенту) →
идемпотентность. Работает только с общими (hazard_id IS NULL) нормами должности.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.medical.service import _load_factor_catalog
from app.domains.sout import cascade as casc
from app.domains.sout.lifecycle import ensure_campaign_open
from app.models.models import MedicalExamKind, MedicalNorm, PPENorm
from app.models.risk import RiskHazard
from app.models.sout import SoutCampaign, SoutFactor, SoutWorkplace
from app.models.tenanting import Tenant
from app.schemas.sout import CascadeMedicalAction, CascadePreview, CascadeResult


def _raw_class(value) -> str | None:
    return value.value if value is not None else None


async def _load_workplace(session: AsyncSession, tenant: Tenant, wid: str) -> SoutWorkplace | None:
    return (
        await session.execute(
            select(SoutWorkplace).where(
                SoutWorkplace.id == wid,
                SoutWorkplace.tenant_id == tenant.id,
                SoutWorkplace.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _load_factors(session: AsyncSession, tenant: Tenant, wid: str):
    return list(
        (
            await session.execute(
                select(SoutFactor).where(
                    SoutFactor.workplace_id == wid, SoutFactor.tenant_id == tenant.id
                )
            )
        ).scalars().all()
    )


async def _load_hazard_meta(session: AsyncSession, tenant: Tenant, hazard_ids):
    if not hazard_ids:
        return {}
    rows = (
        await session.execute(
            select(RiskHazard.id, RiskHazard.title, RiskHazard.medical_factor_code).where(
                RiskHazard.id.in_(hazard_ids), RiskHazard.tenant_id == tenant.id
            )
        )
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def _load_general_med_norms(session: AsyncSession, tenant: Tenant, position_id: str):
    """{exam_kind_value: working_conditions_class} для общих (hazard_id IS NULL) норм."""
    rows = (
        await session.execute(
            select(MedicalNorm.exam_kind, MedicalNorm.working_conditions_class).where(
                MedicalNorm.tenant_id == tenant.id,
                MedicalNorm.position_id == position_id,
                MedicalNorm.hazard_id.is_(None),
            )
        )
    ).all()
    return {r[0].value: r[1] for r in rows}


async def _load_ppe_pairs(session: AsyncSession, tenant: Tenant, position_id: str):
    rows = (
        await session.execute(
            select(PPENorm.position_id, PPENorm.hazard_id).where(
                PPENorm.tenant_id == tenant.id, PPENorm.position_id == position_id
            )
        )
    ).all()
    return {(r[0], r[1]) for r in rows}


async def _build_plan(session: AsyncSession, tenant: Tenant, wp: SoutWorkplace) -> casc.CascadePlan:
    assessed = _raw_class(wp.assessed_class)
    if wp.position_id is None:
        return casc.CascadePlan(assessed_class=assessed)
    factors = await _load_factors(session, tenant, wp.id)
    hazard_ids = {f.hazard_id for f in factors if f.hazard_id is not None}
    hazard_meta = await _load_hazard_meta(session, tenant, hazard_ids)
    catalog = await _load_factor_catalog(session, tenant_id=str(tenant.id))
    existing_med = await _load_general_med_norms(session, tenant, wp.position_id)
    ppe_pairs = await _load_ppe_pairs(session, tenant, wp.position_id)
    return casc.build_cascade_plan(
        assessed_class=assessed, position_id=wp.position_id, factors=factors,
        hazard_meta=hazard_meta, factor_catalog=catalog,
        existing_med_norms=existing_med, existing_ppe_pairs=ppe_pairs,
    )


def _to_preview(plan: casc.CascadePlan) -> CascadePreview:
    medical = [
        CascadeMedicalAction(
            exam_kind=a.exam_kind, op=a.op, periodicity_months=a.periodicity_months,
            interval_days=a.interval_days, target_class=a.target_class,
            current_class=a.current_class, factor_codes=a.factor_codes, reason=a.reason,
        )
        for a in plan.medical
    ]
    can_apply = any(a.op in ("create", "reclass") for a in plan.medical)
    # plan.ppe_advisory items are already PpeNormSuggestion (pydantic) instances —
    # build_ppe_norm_suggestions returns the schema directly.
    return CascadePreview(
        assessed_class=plan.assessed_class, can_apply=can_apply,
        medical=medical, ppe_advisory=list(plan.ppe_advisory),
    )


async def preview_cascade(
    session: AsyncSession, tenant: Tenant, wid: str
) -> CascadePreview | None:
    wp = await _load_workplace(session, tenant, wid)
    if wp is None:
        return None
    plan = await _build_plan(session, tenant, wp)
    return _to_preview(plan)


async def apply_cascade(
    session: AsyncSession, tenant: Tenant, wid: str
) -> CascadeResult | None:
    """Применить каскад. Бросает CampaignTransitionError если кампания закрыта."""
    wp = await _load_workplace(session, tenant, wid)
    if wp is None:
        return None
    campaign = (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.id == wp.campaign_id, SoutCampaign.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if campaign is None:
        return None
    ensure_campaign_open(campaign.status)  # CampaignTransitionError → 409 в роуте

    plan = await _build_plan(session, tenant, wp)
    created = reclassified = conflicts = 0
    for action in plan.medical:
        if action.op == "create":
            session.add(
                MedicalNorm(
                    tenant_id=tenant.id, position_id=wp.position_id,
                    exam_kind=MedicalExamKind(action.exam_kind), hazard_id=None,
                    interval_days=action.interval_days,
                    working_conditions_class=action.target_class,
                )
            )
            created += 1
        elif action.op == "reclass":
            norm = (
                await session.execute(
                    select(MedicalNorm).where(
                        MedicalNorm.tenant_id == tenant.id,
                        MedicalNorm.position_id == wp.position_id,
                        MedicalNorm.hazard_id.is_(None),
                        MedicalNorm.exam_kind == MedicalExamKind(action.exam_kind),
                    )
                )
            ).scalars().first()
            if norm is not None and norm.working_conditions_class in (None, ""):
                norm.working_conditions_class = action.target_class
                reclassified += 1
        elif action.op == "conflict":
            conflicts += 1
    await session.flush()
    return CascadeResult(
        created=created, reclassified=reclassified, conflicts=conflicts,
        ppe_advisory_count=len(plan.ppe_advisory),
    )
