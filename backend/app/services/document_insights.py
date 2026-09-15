"""Сравнение версий документа и карта зависимостей (шаблон, НПА, профиль)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.npa.scope import get_visible_act
from app.models.document import Document, DocumentVersion
from app.models.models import NPABinding, NpaBindingTarget, Template, TemplateVersion


def _canonical_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return value


def diff_version_data_json(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    """Плоское сравнение ключей верхнего уровня data_json (значения нормализованы для вложенных структур)."""

    keys = set(left) | set(right)
    rows: list[dict[str, Any]] = []
    for key in sorted(keys):
        l_val = left.get(key)
        r_val = right.get(key)
        if key not in left:
            rows.append({"field": key, "before": None, "after": r_val, "change": "added"})
        elif key not in right:
            rows.append({"field": key, "before": l_val, "after": None, "change": "removed"})
        else:
            lc, rc = _canonical_value(l_val), _canonical_value(r_val)
            if lc != rc:
                rows.append({"field": key, "before": l_val, "after": r_val, "change": "modified"})
    return rows


async def load_document_versions_for_compare(
    session: AsyncSession,
    *,
    tenant_id: str,
    document_id: str,
    left_version_id: str,
    right_version_id: str,
) -> tuple[DocumentVersion, DocumentVersion]:
    stmt = (
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.id == document_id)
        .options(selectinload(Document.versions))
    )
    document = (await session.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise ValueError("document_not_found")

    by_id = {v.id: v for v in document.versions}
    left = by_id.get(left_version_id)
    right = by_id.get(right_version_id)
    if left is None or right is None:
        raise ValueError("version_not_found")
    return left, right


async def build_document_dependency_map(
    session: AsyncSession, *, tenant_id: str, document: Document
) -> dict[str, Any]:
    """Собирает узлы: шаблон, версия шаблона, привязки НПА, подсказка профиля из версии шаблона."""

    template: Template | None = document.template
    if template is None and document.template_id:
        t_row = await session.get(Template, document.template_id)
        if t_row is not None and str(t_row.tenant_id) == str(tenant_id):
            template = t_row

    tv: TemplateVersion | None = document.template_version
    if tv is None and document.template_version_id:
        v_row = await session.get(TemplateVersion, document.template_version_id)
        if v_row is not None and str(v_row.tenant_id) == str(tenant_id):
            tv = v_row

    npa_bindings_raw: list[NPABinding] = []
    seen_binding_ids: set[str] = set()
    if tv is not None:
        q1 = await session.execute(
            select(NPABinding).where(
                NPABinding.tenant_id == tenant_id,
                NPABinding.template_version_id == tv.id,
            )
        )
        for row in q1.scalars().all():
            if row.id not in seen_binding_ids:
                seen_binding_ids.add(row.id)
                npa_bindings_raw.append(row)
    q2 = await session.execute(
        select(NPABinding).where(
            NPABinding.tenant_id == tenant_id,
            NPABinding.entity_type == NpaBindingTarget.DOCUMENT,
            NPABinding.entity_id == document.id,
        )
    )
    for row in q2.scalars().all():
        if row.id not in seen_binding_ids:
            seen_binding_ids.add(row.id)
            npa_bindings_raw.append(row)

    npa_payload: list[dict[str, Any]] = []
    for binding in npa_bindings_raw:
        # Срез-201: у акта появился владелец — общий реестр (NULL) или сам
        # арендатор. Комментарий среза-142 «проверять принадлежность нечего»
        # с этого момента неверен, и проверка идёт через единственное место.
        npa = await get_visible_act(session, binding.npa_id, str(tenant_id))
        npa_payload.append(
            {
                "binding_id": binding.id,
                "npa_id": binding.npa_id,
                "npa_code": npa.code if npa else "",
                "npa_title": npa.title if npa else "",
                "ref": binding.ref,
                "entity_type": (
                    binding.entity_type.value
                    if hasattr(binding.entity_type, "value")
                    else str(binding.entity_type)
                ),
            }
        )

    profile_hint = tv.profile if tv and tv.profile else None

    return {
        "template": (
            None
            if not template
            else {
                "id": template.id,
                "name": template.name,
                "code": template.code,
                "status": (
                    template.status.value
                    if hasattr(template.status, "value")
                    else str(template.status)
                ),
            }
        ),
        "template_version": (
            None
            if not tv
            else {
                "id": tv.id,
                "version": tv.version,
                "status": tv.status.value if hasattr(tv.status, "value") else str(tv.status),
                "document_type": tv.document_type,
            }
        ),
        "npa_bindings": npa_payload,
        "pipeline_profile_hint": profile_hint,
    }
