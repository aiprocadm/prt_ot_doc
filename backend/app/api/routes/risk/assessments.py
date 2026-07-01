"""Risk endpoints — assessment create/read (ARCH-4 slice 6 split)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import cast
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.routes.risk._common import (
    AssessIn,
    AssessItemIn,
    EditorAccess,
    RiskAssessmentItemOut,
    RiskAssessmentOut,
    RiskAssessmentResponse,
    SessionDep,
    TenantDep,
    _band_from_definition,
    _get_or_create_default_methodology,
    _get_tenant_entity,
    _resolve_controls,
    _risk_bad_request,
    engine_router,
    logger,
)
from app.core.idempotency import compute_request_hash
from app.core.metrics import get_metrics
from app.core.security import AuthContext, get_auth_ctx
from app.models.models import (
    Company,
    DocumentPack,
    Person,
    Position,
    RiskMethodology,
    Site,
    Workplace,
)
from app.models.risk import (
    RiskActionPlan,
    RiskActionPlanItem,
    RiskAssessment,
    RiskAssessmentItem,
    RiskCard,
    RiskHazard,
)
from app.modules.risk import score_band
from app.services.events import EventType
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.outbox import OutboxService


@engine_router.post(
    "/assess", response_model=RiskAssessmentResponse, status_code=status.HTTP_200_OK
)
async def assess(
    payload: AssessIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    auth: AuthContext = Depends(get_auth_ctx),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RiskAssessmentResponse:
    tenant_id = str(tenant.id)
    idempotency: IdempotencyService | None = None
    idempotency_record = None
    if idempotency_key is not None:
        normalized_key = normalize_idempotency_key(idempotency_key)
        idem_state = getattr(request.state, "idempotency", {})
        request_hash = idem_state.get("fingerprint")
        if request_hash is None:
            request_hash = compute_request_hash(payload)
            request.state.idempotency = {"key": normalized_key, "fingerprint": request_hash}
        idempotency = IdempotencyService(
            session=session,
            tenant_id=tenant_id,
            endpoint="risk.assess",
        )
        idempotency_record, created_record = await idempotency.acquire(
            key=normalized_key,
            request_hash=request_hash,
            method=request.method.upper(),
            path=request.url.path,
        )
        if not created_record:
            return await idempotency.respond_from_store(
                idempotency_record, model=RiskAssessmentResponse, response=response
            )

    if payload.company_id:
        await _get_tenant_entity(session, Company, tenant_id, payload.company_id)
    if payload.place_id:
        await _get_tenant_entity(session, Site, tenant_id, payload.place_id)
    if payload.workplace_id:
        await _get_tenant_entity(session, Workplace, tenant_id, payload.workplace_id)
    if payload.position_id:
        await _get_tenant_entity(session, Position, tenant_id, payload.position_id)
    if payload.employee_id:
        await _get_tenant_entity(session, Person, tenant_id, payload.employee_id)
    if payload.document_pack_id:
        await _get_tenant_entity(session, DocumentPack, tenant_id, payload.document_pack_id)

    if payload.items:
        items_payload = payload.items
    else:
        if payload.hazard_code is None or payload.before is None:
            raise _risk_bad_request("hazard_code and before are required")
        severity_before, likelihood_before = payload.before
        items_payload = [
            AssessItemIn(
                hazard_code=payload.hazard_code,
                probability=likelihood_before,
                severity=severity_before,
            )
        ]

    hazard_codes = [item.hazard_code for item in items_payload]
    hazards = (
        (
            await session.execute(
                select(RiskHazard).where(
                    RiskHazard.tenant_id == tenant_id,
                    RiskHazard.code.in_(hazard_codes),
                )
            )
        )
        .scalars()
        .all()
    )
    hazard_lookup = {hazard.code: hazard for hazard in hazards}
    missing = [code for code in hazard_codes if code not in hazard_lookup]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Hazard not found: {', '.join(sorted(missing))}"
        )

    if payload.methodology_id:
        methodology = await _get_tenant_entity(
            session, RiskMethodology, tenant_id, payload.methodology_id
        )
    else:
        methodology = await _get_or_create_default_methodology(session, tenant_id)
    definition = methodology.definition or {}

    assessment_key = payload.assessment_key or str(uuid4())
    assessment_version = payload.assessment_version or 1
    if payload.assessment_key:
        existing_assessment = (
            await session.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.tenant_id == tenant_id,
                    RiskAssessment.assessment_key == assessment_key,
                    RiskAssessment.assessment_version == assessment_version,
                )
                .options(selectinload(RiskAssessment.risk_cards))
                .options(selectinload(RiskAssessment.action_plan))
            )
        ).scalar_one_or_none()
        if existing_assessment is not None:
            cards = existing_assessment.risk_cards
            plan = existing_assessment.action_plan
            response_payload = RiskAssessmentResponse(
                assessment_id=existing_assessment.id,
                assessment_key=existing_assessment.assessment_key,
                assessment_version=existing_assessment.assessment_version,
                risk_card_ids=[card.id for card in cards],
                action_plan_id=plan.id if plan else None,
            )
            if idempotency and idempotency_record:
                await idempotency.store_success(
                    idempotency_record,
                    status_code=status.HTTP_200_OK,
                    body=response_payload.model_dump(mode="json"),
                )
            return response_payload

    before_pair = payload.before
    if before_pair is None:
        before_pair = (items_payload[0].severity, items_payload[0].probability)
    severity_before, likelihood_before = before_pair
    score_before, band_before = await score_band(
        session, tenant_id, severity_before, likelihood_before
    )

    if payload.items is None:
        if payload.after is not None:
            severity_after, likelihood_after = payload.after
        else:
            severity_after, likelihood_after = severity_before, max(1, likelihood_before - 1)
    else:
        severity_after, likelihood_after = severity_before, likelihood_before
    score_after, band_after = await score_band(session, tenant_id, severity_after, likelihood_after)

    controls_json = json.dumps(payload.controls, ensure_ascii=False)
    created_by = payload.created_by or auth.sub
    controls_lookup = await _resolve_controls(
        session, tenant_id=tenant_id, control_codes=payload.controls
    )
    control_steps: list[dict[str, object]] = []
    for code in payload.controls:
        control = controls_lookup.get(code)
        if control is None:
            control_steps.append(
                {
                    "code": code,
                    "title": code,
                    "type": "org",
                    "description": None,
                    "status": "planned",
                    "missing": True,
                }
            )
            continue
        control_steps.append(
            {
                "code": control.code,
                "title": control.title,
                "type": control.type,
                "description": control.description,
                "status": "planned",
            }
        )

    first_hazard = hazard_lookup[items_payload[0].hazard_code]
    assessment = RiskAssessment(
        tenant_id=tenant_id,
        assessment_key=assessment_key,
        assessment_version=assessment_version,
        methodology_id=methodology.id,
        methodology_version=methodology.version,
        company_id=payload.company_id,
        place_id=payload.place_id,
        workplace_id=payload.workplace_id,
        position_id=payload.position_id,
        employee_id=payload.employee_id,
        document_pack_id=payload.document_pack_id,
        job_title=payload.job_title,
        hazard_id=first_hazard.id,
        severity_before=severity_before,
        likelihood_before=likelihood_before,
        score_before=score_before,
        band_before=band_before,
        controls=controls_json,
        risk_card=None,
        severity_after=severity_after,
        likelihood_after=likelihood_after,
        score_after=score_after,
        band_after=band_after,
        created_by=created_by,
    )
    session.add(assessment)
    await session.flush()

    item_rows: list[RiskAssessmentItem] = []
    item_payloads: list[dict[str, object]] = []
    for item in items_payload:
        hazard = hazard_lookup[item.hazard_code]
        score = int(item.probability) * int(item.severity)
        level = _band_from_definition(definition, score)
        item_rows.append(
            RiskAssessmentItem(
                tenant_id=tenant_id,
                assessment_id=assessment.id,
                hazard_id=hazard.id,
                probability=item.probability,
                severity=item.severity,
                score=score,
                level=level,
                methodology_id=methodology.id,
                methodology_version=methodology.version,
            )
        )
        item_payloads.append(
            {
                "hazard_id": hazard.id,
                "hazard_code": hazard.code,
                "hazard_title": hazard.title,
                "probability": item.probability,
                "severity": item.severity,
                "score": score,
                "level": level,
            }
        )
    session.add_all(item_rows)

    counts_by_level: dict[str, int] = {}
    for payload_item in item_payloads:
        level = cast(str, payload_item["level"])
        counts_by_level[level] = counts_by_level.get(level, 0) + 1
    sorted_items = sorted(
        item_payloads,
        key=lambda entry: (-int(entry["score"]), str(entry["hazard_code"])),
    )

    summary = {
        "assessment_id": assessment.id,
        "methodology": {
            "id": str(methodology.id),
            "version": methodology.version,
        },
        "scope": {
            "company_id": payload.company_id,
            "place_id": payload.place_id,
            "workplace_id": payload.workplace_id,
            "position_id": payload.position_id,
            "employee_id": payload.employee_id,
            "document_pack_id": payload.document_pack_id,
        },
        "counts_by_level": counts_by_level,
        "items": sorted_items,
    }

    risk_card = RiskCard(
        tenant_id=tenant_id,
        assessment_id=assessment.id,
        company_id=payload.company_id,
        site_id=payload.place_id,
        workplace_id=payload.workplace_id,
        position_id=payload.position_id,
        employee_id=payload.employee_id,
        methodology_id=methodology.id,
        methodology_version=methodology.version,
        summary=summary,
    )
    session.add(risk_card)

    action_plan = RiskActionPlan(
        tenant_id=tenant_id,
        assessment_id=assessment.id,
        company_id=payload.company_id,
        site_id=payload.place_id,
        workplace_id=payload.workplace_id,
        position_id=payload.position_id,
        employee_id=payload.employee_id,
        methodology_id=methodology.id,
        methodology_version=methodology.version,
        status="open",
    )
    session.add(action_plan)
    await session.flush()

    created_at = assessment.created_at
    plan_items: list[RiskActionPlanItem] = []
    for item in sorted_items:
        hazard_id = cast(str, item["hazard_id"])
        hazard = hazard_lookup[cast(str, item["hazard_code"])]
        measures = list(hazard.recommended_measures or [])
        if not measures and control_steps:
            measures = [
                {
                    "text": step.get("title") or step.get("code") or str(step),
                    "owner_role": None,
                    "owner_id": None,
                    "due_in_days": 30,
                }
                for step in control_steps
            ]
        if not measures:
            measures = [
                {
                    "text": f"Review hazard: {hazard.title}",
                    "owner_role": None,
                    "owner_id": None,
                    "due_in_days": 30,
                }
            ]
        for measure in sorted(measures, key=lambda entry: str(entry.get("text", ""))):
            due_in_days = measure.get("due_in_days")
            due_date: date | None = None
            if isinstance(due_in_days, int):
                due_date = (created_at + timedelta(days=due_in_days)).date()
            plan_items.append(
                RiskActionPlanItem(
                    tenant_id=tenant_id,
                    plan_id=action_plan.id,
                    assessment_id=assessment.id,
                    hazard_id=hazard_id,
                    measure_text=str(measure.get("text") or ""),
                    owner_role=cast(str | None, measure.get("owner_role")),
                    owner_id=cast(str | None, measure.get("owner_id")),
                    due_date=due_date,
                    status="planned",
                    methodology_id=methodology.id,
                    methodology_version=methodology.version,
                )
            )
    session.add_all(plan_items)

    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=tenant_id,
        event_type=EventType.RISK_ASSESSED.value,
        payload={
            "tenant_id": tenant_id,
            "actor_id": created_by,
            "occurred_at": assessment.created_at,
            "risk_assessment_id": assessment.id,
            "hazard_code": first_hazard.code,
            "company_id": payload.company_id,
            "place_id": payload.place_id,
            "position_id": payload.position_id,
            "document_pack_id": payload.document_pack_id,
            "before": {
                "severity": severity_before,
                "likelihood": likelihood_before,
                "score": score_before,
                "band": band_before,
            },
            "after": {
                "severity": severity_after,
                "likelihood": likelihood_after,
                "score": score_after,
                "band": band_after,
            },
            "controls": control_steps,
            "action_plan": {
                "id": action_plan.id,
                "risk_card_ids": [risk_card.id],
                "items": [
                    {
                        "id": plan_item.id,
                        "hazard_id": plan_item.hazard_id,
                        "measure_text": plan_item.measure_text,
                        "due_date": plan_item.due_date,
                        "status": plan_item.status,
                    }
                    for plan_item in plan_items
                ],
            },
        },
    )

    metrics = get_metrics()
    metrics.risk_assessment_total.inc()
    metrics.risk_cards_created_total.inc()
    metrics.action_plan_items_created_total.inc(len(plan_items))

    await session.commit()

    response_payload = RiskAssessmentResponse(
        assessment_id=assessment.id,
        assessment_key=assessment.assessment_key,
        assessment_version=assessment.assessment_version,
        risk_card_ids=[risk_card.id],
        action_plan_id=action_plan.id,
    )
    if idempotency and idempotency_record:
        await idempotency.store_success(
            idempotency_record,
            status_code=status.HTTP_200_OK,
            body=response_payload.model_dump(mode="json"),
        )
    logger.info(
        "risk.assessment.completed",
        extra={
            "assessment_id": assessment.id,
            "tenant_id": tenant_id,
            "scope": {
                "company_id": payload.company_id,
                "place_id": payload.place_id,
                "workplace_id": payload.workplace_id,
                "position_id": payload.position_id,
                "employee_id": payload.employee_id,
            },
            "methodology_version": methodology.version,
        },
    )
    return response_payload


@engine_router.get("/assessments/{assessment_id}", response_model=RiskAssessmentOut)
async def get_assessment(
    assessment_id: str,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> RiskAssessmentOut:
    tenant_id = str(tenant.id)
    stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.tenant_id == tenant_id, RiskAssessment.id == assessment_id)
        .options(selectinload(RiskAssessment.items).selectinload(RiskAssessmentItem.hazard))
        .options(selectinload(RiskAssessment.risk_cards))
        .options(selectinload(RiskAssessment.action_plan).selectinload(RiskActionPlan.items))
    )
    assessment = (await session.execute(stmt)).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")

    items = sorted(
        assessment.items,
        key=lambda item: (-item.score, item.hazard.code if item.hazard else ""),
    )
    item_payloads = [
        RiskAssessmentItemOut(
            id=item.id,
            hazard_id=item.hazard_id,
            hazard_code=item.hazard.code if item.hazard else "",
            hazard_title=item.hazard.title if item.hazard else "",
            probability=item.probability,
            severity=item.severity,
            score=item.score,
            level=item.level,
        )
        for item in items
    ]
    risk_card_ids = [card.id for card in assessment.risk_cards]
    plan = assessment.action_plan
    return RiskAssessmentOut(
        id=assessment.id,
        assessment_key=assessment.assessment_key,
        assessment_version=assessment.assessment_version,
        methodology_id=assessment.methodology_id,
        methodology_version=assessment.methodology_version,
        company_id=assessment.company_id,
        place_id=assessment.place_id,
        workplace_id=assessment.workplace_id,
        position_id=assessment.position_id,
        employee_id=assessment.employee_id,
        document_pack_id=assessment.document_pack_id,
        items=item_payloads,
        risk_card_ids=risk_card_ids,
        action_plan_id=plan.id if plan else None,
    )
