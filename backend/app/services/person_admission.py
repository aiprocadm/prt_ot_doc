"""Shared person-admission guard.

Extracted from ``tasks.py::_enforce_person_invariants`` (Task 7.1) and
extended with suspension-block and norm-aware medical checks (Task 7.2).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.medical import lifecycle as lc
from app.domains.ppe import lifecycle as ppe_lc
from app.models.models import (
    MedicalExam,
    MedicalNorm,
    MedicalSuspension,
    MedicalSuspensionStatus,
    Person,
    PositionHazardLink,
    PPEIssue,
    PPEIssueStatus,
    PPENorm,
    Training,
    TrainingStatus,
)
from app.modules.ppe.services import NormItem, PPENormService


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def enforce_person_admission(
    session: AsyncSession,
    *,
    tenant_scope: tuple[str, ...],
    persons: list[Person],
) -> None:
    """Enforce all person-admission invariants.

    Checks training, medical examination, PPE, active medical suspension, and
    (when medical norms exist for the person's position) per-kind norm-aware
    medical exam completeness. The PPE check is likewise norm-aware: when PPE
    norms exist for the person's position, every 766н card line must avoid
    missing/overdue (СИЗ Срез-2); without norms the legacy any-active-issue
    check applies.

    Raises:
        ValueError: ``{"code": "requirements_not_met", "details": [...]}``
            when any person fails one or more checks.
    """
    if not persons:
        return

    now = datetime.now(timezone.utc)
    person_ids = [person.id for person in persons]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    training_stmt = (
        select(Training.person_id, Training.expires_at)
        .where(
            Training.person_id.in_(person_ids),
            Training.tenant_id.in_(tenant_scope),
            Training.status == TrainingStatus.COMPLETED,
            Training.expires_at.is_not(None),
        )
        .order_by(Training.person_id)
    )

    # ------------------------------------------------------------------
    # Medical exam (legacy: any valid exam; upgraded per-person below)
    # ------------------------------------------------------------------
    medical_stmt = (
        select(MedicalExam.person_id, MedicalExam.valid_until)
        .where(
            MedicalExam.person_id.in_(person_ids),
            MedicalExam.tenant_id.in_(tenant_scope),
            MedicalExam.deleted_at.is_(None),
        )
        .order_by(MedicalExam.person_id)
    )

    # ------------------------------------------------------------------
    # PPE
    # ------------------------------------------------------------------
    ppe_stmt = (
        select(PPEIssue.person_id, PPEIssue.expires_at)
        .where(
            PPEIssue.person_id.in_(person_ids),
            PPEIssue.tenant_id.in_(tenant_scope),
            PPEIssue.status == PPEIssueStatus.ISSUED,
            PPEIssue.expires_at.is_not(None),
        )
        .order_by(PPEIssue.person_id)
    )

    training_rows = (await session.execute(training_stmt)).all()
    medical_rows = (await session.execute(medical_stmt)).all()
    ppe_rows = (await session.execute(ppe_stmt)).all()

    valid_training: set[str] = set()
    for person_id, expires_at in training_rows:
        expiry = _normalize_datetime(expires_at)
        if expiry and expiry > now:
            valid_training.add(person_id)

    valid_medical: set[str] = set()
    for person_id, valid_until in medical_rows:
        if valid_until and valid_until >= now.date():
            valid_medical.add(person_id)

    valid_ppe: set[str] = set()
    for person_id, expires_at in ppe_rows:
        expires = _normalize_datetime(expires_at)
        if expires and expires > now:
            valid_ppe.add(person_id)

    # ------------------------------------------------------------------
    # Task 7.2 (a) — active medical suspensions
    # ------------------------------------------------------------------
    susp_rows = (
        await session.execute(
            select(MedicalSuspension.person_id).where(
                MedicalSuspension.person_id.in_(person_ids),
                MedicalSuspension.tenant_id.in_(tenant_scope),
                MedicalSuspension.deleted_at.is_(None),
                MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE,
            )
        )
    ).all()
    suspended: set[str] = {row[0] for row in susp_rows}

    # ------------------------------------------------------------------
    # Task 7.2 (b) — norm-aware medical (per exam-kind when norms exist)
    #
    # We avoid lazy relationship access entirely: collect position_ids from
    # persons, then query PositionHazardLink with an explicit SELECT to build
    # {position_id: set(hazard_id)} — no ORM relationship traversal needed.
    # ------------------------------------------------------------------
    norm_rows = (
        await session.execute(
            select(
                MedicalNorm.position_id,
                MedicalNorm.hazard_id,
                MedicalNorm.working_conditions_class,
                MedicalNorm.exam_kind,
            ).where(MedicalNorm.tenant_id.in_(tenant_scope))
        )
    ).all()
    norms: list[lc.NormTuple] = [(r[0], r[1], r[2], r[3]) for r in norm_rows]
    positions_with_norms: set[str] = {r[0] for r in norm_rows}

    # Latest valid_until per (person_id, exam_kind) — for norm-aware path
    ex_rows = (
        await session.execute(
            select(
                MedicalExam.person_id,
                MedicalExam.exam_kind,
                func.max(MedicalExam.valid_until),
            )
            .where(
                MedicalExam.person_id.in_(person_ids),
                MedicalExam.tenant_id.in_(tenant_scope),
                MedicalExam.deleted_at.is_(None),
                MedicalExam.exam_kind.is_not(None),
            )
            .group_by(MedicalExam.person_id, MedicalExam.exam_kind)
        )
    ).all()
    latest_by_kind: dict[tuple[str, str], date | None] = {
        (pid, (kind.value if hasattr(kind, "value") else kind)): vu for pid, kind, vu in ex_rows
    }

    # Hazard map: position_id -> set of hazard_id (explicit query, no lazy load)
    position_ids: list[str] = list({person.position_id for person in persons if person.position_id})
    position_hazards: dict[str, set[str]] = {pid: set() for pid in position_ids}
    if position_ids:
        ph_rows = (
            await session.execute(
                select(
                    PositionHazardLink.position_id,
                    PositionHazardLink.hazard_id,
                ).where(
                    PositionHazardLink.position_id.in_(position_ids),
                    PositionHazardLink.tenant_id.in_(tenant_scope),
                )
            )
        ).all()
        for ph_pos, ph_haz in ph_rows:
            position_hazards.setdefault(ph_pos, set()).add(ph_haz)

    # ------------------------------------------------------------------
    # СИЗ Срез-2 — norm-aware PPE (mirror of the medical norm-aware path):
    # when PPE norms exist for the person's position, every 766н card line
    # must avoid missing/overdue (ok/due_soon pass); otherwise the legacy
    # any-active-issue check stays in force.
    # ------------------------------------------------------------------
    ppe_norm_rows: Sequence[Any] = []
    if position_ids:
        ppe_norm_rows = (
            await session.execute(
                select(
                    PPENorm.position_id,
                    PPENorm.item_id,
                    PPENorm.item_name,
                    PPENorm.quantity,
                ).where(
                    PPENorm.tenant_id.in_(tenant_scope),
                    PPENorm.position_id.in_(position_ids),
                )
            )
        ).all()

    norms_by_position: dict[str, list[tuple[str | None, str, int]]] = {}
    for npos_id, nitem_id, nitem_name, nquantity in ppe_norm_rows:
        norms_by_position.setdefault(npos_id, []).append((nitem_id, nitem_name, nquantity))

    # Required card lines per position — same fold as build_personal_card_766n:
    # required_union (max per catalog key) + best-norm metadata per key.
    ppe_required_by_position: dict[str, list[tuple[str | None, str, int]]] = {}
    for npos_id, pos_norms in norms_by_position.items():
        norm_items = [
            NormItem(
                applies_to_type="position",
                applies_to_id=npos_id,
                ppe_catalog_id=ppe_lc.norm_line_key(nitem_id, nitem_name),
                quantity=float(nquantity),
                period_months=None,
            )
            for nitem_id, nitem_name, nquantity in pos_norms
        ]
        required_qty = PPENormService.required_union(
            position_id=npos_id,
            workplace_id=None,
            hazard_ids=set(),
            norm_items=norm_items,
        )
        line_meta: dict[str, tuple[str | None, str, int]] = {}
        for nitem_id, nitem_name, nquantity in pos_norms:
            key = ppe_lc.norm_line_key(nitem_id, nitem_name)
            kept = line_meta.get(key)
            if kept is None or nquantity > kept[2]:
                line_meta[key] = (nitem_id, nitem_name, nquantity)
        ppe_required_by_position[npos_id] = [
            (line_meta[key][0], line_meta[key][1], int(qty)) for key, qty in required_qty.items()
        ]

    normed_person_ids = [
        person.id
        for person in persons
        if person.position_id and person.position_id in ppe_required_by_position
    ]
    # person_id -> (issues_by_id, issues_by_name) indexes of IssueView pairs
    ppe_issue_index: dict[
        str,
        tuple[
            dict[str, list[tuple[str, ppe_lc.IssueView]]],
            dict[str, list[tuple[str, ppe_lc.IssueView]]],
        ],
    ] = {}
    if normed_person_ids:
        issue_rows = (
            await session.execute(
                select(
                    PPEIssue.person_id,
                    PPEIssue.id,
                    PPEIssue.item_id,
                    PPEIssue.item_name,
                    PPEIssue.quantity,
                    PPEIssue.expires_at,
                    PPEIssue.status,
                ).where(
                    PPEIssue.person_id.in_(normed_person_ids),
                    PPEIssue.tenant_id.in_(tenant_scope),
                    PPEIssue.deleted_at.is_(None),
                )
            )
        ).all()
        for ipid, iid, iitem_id, iitem_name, iqty, iexpires, istatus in issue_rows:
            view = ppe_lc.IssueView(
                quantity=iqty,
                expires_at=iexpires.date() if iexpires is not None else None,
                status=str(istatus),
            )
            by_id, by_name = ppe_issue_index.setdefault(ipid, ({}, {}))
            if iitem_id:
                by_id.setdefault(iitem_id, []).append((iid, view))
            by_name.setdefault(iitem_name, []).append((iid, view))

    today = now.date()

    # ------------------------------------------------------------------
    # Per-person violation accumulation
    # ------------------------------------------------------------------
    violations: list[dict[str, object]] = []
    for person in persons:
        missing: list[str] = []

        if person.id not in valid_training:
            missing.append("training")

        # Medical — norm-aware or legacy fallback
        pos_id = person.position_id
        if pos_id and pos_id in positions_with_norms:
            hazard_ids = position_hazards.get(pos_id, set())
            wcc = person.working_conditions_class
            required_kinds = lc.resolve_required_kinds(pos_id, wcc, hazard_ids, norms)
            if required_kinds:
                for kind in required_kinds:
                    vu = latest_by_kind.get((person.id, kind.value))
                    if vu is None or vu < today:
                        missing.append("medical_exam")
                        break
            else:
                # Norms exist for position but none apply to this person:
                # fall back to the same legacy check (any valid exam suffices).
                if person.id not in valid_medical:
                    missing.append("medical_exam")
        else:
            # Legacy: any valid medical exam suffices
            if person.id not in valid_medical:
                missing.append("medical_exam")

        # PPE — norm-aware (766н card lines) or legacy fallback
        ppe_required = ppe_required_by_position.get(pos_id) if pos_id else None
        if ppe_required:
            by_id, by_name = ppe_issue_index.get(person.id, ({}, {}))
            for nitem_id, nitem_name, req_qty in ppe_required:
                views = ppe_lc.match_issues_for_norm_line(nitem_id, nitem_name, by_id, by_name)
                line_status = ppe_lc.card_line_status(req_qty, views, today)
                if line_status in ppe_lc.ADMISSION_BLOCKING_STATUSES:
                    missing.append("ppe_issue")
                    break
        else:
            # Legacy: any valid (active, non-expired) issue suffices
            if person.id not in valid_ppe:
                missing.append("ppe_issue")

        # Suspension check (additive — goes after the three standard checks)
        if person.id in suspended:
            missing.append("medical_suspension")

        if missing:
            violations.append({"person_id": person.id, "violations": missing})

    if violations:
        raise ValueError({"code": "requirements_not_met", "details": violations})
