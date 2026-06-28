"""Импорт отчёта СОУТ: файл → diff → preview (read) / apply (запись).

Зеркало services/sout_declaration.py. Пишет ТОЛЬКО в существующие
sout_workplace/sout_factor/sout_class_history (миграции нет). apply повторно
парсит файл (не доверяет клиентскому preview) → идемпотентность по workplace_code."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sout import import_report as imp
from app.domains.sout.service import build_class_history_row
from app.models.sout import SoutClass, SoutFactor, SoutWorkplace
from app.models.tenanting import Tenant
from app.schemas.sout import (
    ImportFactorRow,
    ImportPreview,
    ImportResult,
    ImportWorkplaceRow,
)
from app.services.sout_print import _load_campaign, _raw


class ImportValidationError(Exception):
    """Блокирующие ошибки валидации при apply (→422, без записей)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _to_class(value: str | None) -> SoutClass | None:
    return SoutClass(value) if value else None


async def _load_existing(session: AsyncSession, tenant: Tenant, cid: str):
    rows = list(
        (
            await session.execute(
                select(SoutWorkplace).where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    pairs = [(w.workplace_code, _raw(w.assessed_class)) for w in rows]
    by_code = {w.workplace_code: w for w in rows}
    return pairs, by_code


def _assemble_preview(cid: str, parsed, existing_pairs) -> ImportPreview:
    issues = imp.validate_parsed(parsed)
    diff = imp.diff_campaign(parsed, existing_pairs)
    diff_by_code = {d.workplace_code: d for d in diff}
    rows: list[ImportWorkplaceRow] = []
    error_count = 0
    for i, wp in enumerate(parsed):
        ri = issues[i]
        if ri.errors:
            error_count += 1
        d = diff_by_code[wp.workplace_code]
        rows.append(
            ImportWorkplaceRow(
                row_index=i,
                workplace_code=wp.workplace_code,
                position_name=wp.position_name,
                parsed_class=wp.assessed_class,
                current_class=d.current_class,
                change=d.change,
                factors=[
                    ImportFactorRow(
                        code=f.code, name=f.name,
                        parsed_class=f.measured_class, class_unparsed=f.class_unparsed,
                    )
                    for f in wp.factors
                ],
                errors=ri.errors,
                warnings=ri.warnings,
            )
        )
    for d in diff:
        if d.change == "removed":
            rows.append(
                ImportWorkplaceRow(
                    row_index=-1, workplace_code=d.workplace_code, position_name="",
                    parsed_class=None, current_class=d.current_class, change="removed",
                    factors=[], errors=[], warnings=[],
                )
            )
    counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0}
    for d in diff:
        counts[d.change] += 1
    return ImportPreview(
        campaign_id=cid,
        rows=rows,
        new_count=counts["new"],
        changed_count=counts["changed"],
        unchanged_count=counts["unchanged"],
        removed_count=counts["removed"],
        error_count=error_count,
        can_apply=error_count == 0,
    )


async def preview_import(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, content: bytes, filename: str
) -> ImportPreview | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    parsed = imp.parse_report(content, filename)
    existing_pairs, _ = await _load_existing(session, tenant, campaign_id)
    return _assemble_preview(campaign_id, parsed, existing_pairs)


async def apply_import(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, content: bytes, filename: str
) -> ImportResult | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    parsed = imp.parse_report(content, filename)
    issues = imp.validate_parsed(parsed)
    blocking = [
        f"{parsed[i].workplace_code or f'строка {i + 1}'}: {e}"
        for i, ri in issues.items()
        for e in ri.errors
    ]
    if blocking:
        raise ImportValidationError(blocking)
    existing_pairs, by_code = await _load_existing(session, tenant, campaign_id)
    diff_by_code = {d.workplace_code: d for d in imp.diff_campaign(parsed, existing_pairs)}
    created = updated = skipped = 0
    for wp in parsed:
        change = diff_by_code[wp.workplace_code].change
        if change == "new":
            row = SoutWorkplace(
                tenant_id=tenant.id, campaign_id=campaign_id,
                workplace_code=wp.workplace_code, position_name=wp.position_name,
                assessed_class=_to_class(wp.assessed_class),
            )
            session.add(row)
            await session.flush()
            for f in wp.factors:
                session.add(SoutFactor(
                    tenant_id=tenant.id, workplace_id=row.id,
                    code=f.code, name=f.name, measured_class=_to_class(f.measured_class),
                ))
            hist = build_class_history_row(
                tenant_id=tenant.id, workplace_id=row.id,
                old_class=None, new_class=_to_class(wp.assessed_class),
            )
            if hist is not None:
                session.add(hist)
            created += 1
        elif change == "changed":
            existing = by_code[wp.workplace_code]
            existing.position_name = wp.position_name
            old = existing.assessed_class
            new = _to_class(wp.assessed_class)
            existing.assessed_class = new
            # NOTE: реконсиляция факторов существующего РМ на "changed" отложена (срез-6, spec §7).
            hist = build_class_history_row(
                tenant_id=tenant.id, workplace_id=existing.id, old_class=old, new_class=new,
            )
            if hist is not None:
                session.add(hist)
            updated += 1
        else:
            skipped += 1
    removed_detected = sum(1 for d in diff_by_code.values() if d.change == "removed")
    await session.flush()
    return ImportResult(
        campaign_id=campaign_id, created=created, updated=updated,
        skipped=skipped, removed_detected=removed_detected, errors=[],
    )
