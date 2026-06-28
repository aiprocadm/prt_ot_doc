# P10-04 СОУТ срез-4 «Декларация соответствия» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать результаты СОУТ выгружаемой декларацией соответствия условий труда (ст. 11 ФЗ-426 / Приказ 406н) — read-preview «какие РМ подлежат декларированию» + печатная форма DOCX/PDF, без миграции.

**Architecture:** Зеркало 3-слойного паттерна срез-4а: чистый домен `declaration.py` (eligibility + python-docx сборщик, без I/O) → сервис `sout_declaration.py` (tenant-scoped загрузка + проекция, переиспользует RenderedDoc/PdfRendererUnavailable/_to_pdf из `sout_print`) → 2 эндпоинта в `routes/sout.py` (read-preview + печать) → тонкий фронт. Критерий отбора: класс 1-2 И 0 вредных факторов.

**Tech Stack:** Python 3.12 (CI; локально 3.13.7/.venv), FastAPI, SQLAlchemy async, python-docx; React/Vite/TS, vitest. pytest.

**Спека:** `docs/superpowers/specs/2026-06-28-p10-04-sout-srez4-declaration-design.md`

**Среда запуска тестов (Win):** summary-строка теряется в PowerShell-буфере — судить по EXIT-коду. Запуск: `cd backend && .venv\Scripts\python -m pytest tests/test_X.py -q`. Канон Py3.12 PG CI = финальный гейт.

---

## File Structure

- **Create** `backend/app/domains/sout/declaration.py` — чистый домен: eligibility + dataclasses + `build_declaration_docx`.
- **Create** `backend/app/services/sout_declaration.py` — проекция + `render_declaration` (БД→DOCX/PDF).
- **Modify** `backend/app/schemas/sout.py` — `DeclarationRowRead`, `DeclarationPreview`.
- **Modify** `backend/app/api/routes/sout.py` — эндпоинты `GET /{cid}/declaration` + `GET /{cid}/declaration/print`.
- **Modify** `frontend/src/api/sout.ts` — интерфейсы + `getDeclaration` / `downloadDeclaration`.
- **Modify** `frontend/src/pages/sout/SoutPage.tsx` — секция «Декларация соответствия» в `ReportPanel`.
- **Create** tests: `backend/tests/test_sout_declaration.py`, `backend/tests/test_sout_declaration_service.py`, `backend/tests/test_sout_declaration_api.py`, `frontend/src/__tests__/SoutDeclaration.test.tsx`.

---

## Task 1: Чистый домен `declaration.py` (eligibility + DOCX сборщик)

**Files:**
- Create: `backend/app/domains/sout/declaration.py`
- Test: `backend/tests/test_sout_declaration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_declaration.py
"""Юниты чистого домена декларации СОУТ (без БД, без async)."""
from io import BytesIO

from docx import Document

from app.domains.sout.declaration import (
    DeclarationPrintData,
    DeclarationRow,
    build_declaration_docx,
    evaluate_eligibility,
)
from app.domains.sout.print_form import SoutCardFactorRow


def _text(docx_bytes: bytes) -> str:
    doc = Document(BytesIO(docx_bytes))
    parts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _f(cls: str | None) -> SoutCardFactorRow:
    return SoutCardFactorRow(code=None, name="x", measured_class=cls)


def test_optimal_class_no_factors_is_eligible() -> None:
    assert evaluate_eligibility("optimal", []) == (True, None)


def test_acceptable_class_with_acceptable_factor_is_eligible() -> None:
    assert evaluate_eligibility("acceptable", [_f("acceptable")]) == (True, None)


def test_harmful_class_is_ineligible_with_reason() -> None:
    eligible, reason = evaluate_eligibility("harmful_3_1", [])
    assert eligible is False
    assert "3.1" in reason


def test_missing_class_is_ineligible() -> None:
    eligible, reason = evaluate_eligibility(None, [])
    assert eligible is False
    assert "не проставлен" in reason


def test_class_2_but_harmful_factor_is_ineligible() -> None:
    # Ключевой анти-грабли: класс проставлен 2, но есть фактор 3.1 → дисквалификация.
    eligible, reason = evaluate_eligibility("acceptable", [_f("harmful_3_1")])
    assert eligible is False
    assert "вредный фактор" in reason


def test_build_docx_lists_eligible_rows_and_employer_placeholders() -> None:
    data = DeclarationPrintData(
        org_header="ООО Ромашка",
        generated_at="2026-06-28",
        campaign_name="СОУТ 2026",
        report_number="СОУТ-1",
        report_date="2026-06-01",
        rows=[
            DeclarationRow(
                workplace_code="РМ-02", position_name="Слесарь",
                assessed_class="acceptable", headcount="1",
                report_ref="СОУТ-1 от 2026-06-01", eligible=True, ineligible_reason=None,
            ),
        ],
    )
    txt = _text(build_declaration_docx(data))
    assert "Декларация соответствия условий труда" in txt
    assert "ООО Ромашка" in txt
    assert "ИНН" in txt and "ОГРН" in txt   # плейсхолдеры реквизитов работодателя
    assert "РМ-02" in txt and "Слесарь" in txt
    assert "СОУТ-1" in txt                   # основание (отчёт СОУТ)


def test_build_docx_empty_rows_renders_placeholder() -> None:
    data = DeclarationPrintData(
        org_header="ООО Ромашка", generated_at="2026-06-28",
        campaign_name="Пустая", report_number=None, report_date=None, rows=[],
    )
    txt = _text(build_declaration_docx(data))
    assert "Нет рабочих мест" in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration.py -q`
Expected: FAIL — `ModuleNotFoundError: app.domains.sout.declaration`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domains/sout/declaration.py
"""Чистый домен декларации соответствия условий труда (ст. 11 ФЗ-426, форма 406н).

Без sqlalchemy / без I/O — как print_form.py. Определяет, какие РМ подлежат
декларированию (класс 1-2 И без вредных факторов), и собирает печатную форму.
RU-метки/подсчёт вредных факторов переиспользуются из print_form (один контур)."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

from docx import Document

from app.domains.sout.print_form import (
    SoutCardFactorRow,
    class_label,
    harmful_factor_count,
)

#: Классы условий труда, при которых РМ подлежит декларированию (1 и 2).
DECLARABLE_CLASSES = frozenset({"optimal", "acceptable"})


def evaluate_eligibility(
    assessed_class: str | None, factors: list[SoutCardFactorRow]
) -> tuple[bool, str | None]:
    """Подлежит ли РМ декларированию. Возвращает (eligible, ineligible_reason).

    Консервативно-юридический критерий: любой вредный фактор (класс 3.1+)
    дисквалифицирует РМ, даже если итоговый класс проставлен 1-2.
    """
    if assessed_class is None:
        return False, "класс условий труда не проставлен"
    if assessed_class not in DECLARABLE_CLASSES:
        return False, f"класс {class_label(assessed_class)} — вредные/опасные условия"
    if harmful_factor_count(factors) > 0:
        return False, "выявлен вредный фактор (класс 3.1+)"
    return True, None


@dataclass
class DeclarationRow:
    workplace_code: str
    position_name: str
    assessed_class: str | None
    headcount: str          # "1" если есть person_id, иначе "—"
    report_ref: str | None
    eligible: bool
    ineligible_reason: str | None


@dataclass
class DeclarationPrintData:
    org_header: str
    generated_at: str | None
    employer_inn: str | None = None
    employer_ogrn: str | None = None
    employer_address: str | None = None
    campaign_name: str = ""
    report_number: str | None = None
    report_date: str | None = None
    rows: list[DeclarationRow] = field(default_factory=list)  # только eligible идут в печать


def _kv(doc, label: str, value: str | None) -> None:
    doc.add_paragraph(f"{label}: {value if value else '____________________'}")


def build_declaration_docx(data: DeclarationPrintData) -> bytes:
    doc = Document()
    doc.add_heading(
        "Декларация соответствия условий труда государственным нормативным "
        "требованиям охраны труда",
        level=0,
    )
    doc.add_paragraph(f"Наименование работодателя: {data.org_header}")
    _kv(doc, "ИНН", data.employer_inn)
    _kv(doc, "ОГРН", data.employer_ogrn)
    _kv(doc, "Адрес", data.employer_address)

    basis = None
    if data.report_number or data.report_date:
        basis = " ".join(
            p for p in [
                f"№ {data.report_number}" if data.report_number else None,
                f"от {data.report_date}" if data.report_date else None,
            ] if p
        )
    doc.add_paragraph(f"Основание — отчёт о проведении СОУТ: {basis or '____________________'}")

    doc.add_heading("Рабочие места, подлежащие декларированию", level=1)
    if data.rows:
        tbl = doc.add_table(rows=1, cols=5)
        tbl.style = "Table Grid"
        for i, title in enumerate(
            ["№", "Код РМ", "Должность", "Численность", "Реквизиты отчёта СОУТ"]
        ):
            tbl.rows[0].cells[i].text = title
        for idx, r in enumerate(data.rows, start=1):
            cells = tbl.add_row().cells
            cells[0].text = str(idx)
            cells[1].text = r.workplace_code
            cells[2].text = r.position_name
            cells[3].text = r.headcount
            cells[4].text = r.report_ref or "—"
    else:
        doc.add_paragraph("Нет рабочих мест, подлежащих декларированию.")

    # Срок действия декларации регулируется ст. 11 ФЗ-426.
    # TODO (юр.): точную формулировку срока/условий прекращения сверить с юристом.
    doc.add_paragraph(
        "Декларация подаётся в территориальный орган федерального органа "
        "исполнительной власти (Роструд). Срок действия — согласно ст. 11 ФЗ-426."
    )
    doc.add_paragraph("Руководитель: ____________________ / ____________________")
    _kv(doc, "Дата формирования", data.generated_at)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/sout/declaration.py backend/tests/test_sout_declaration.py
git commit -m "feat(sout): declaration eligibility + DOCX builder (срез-4)"
```

---

## Task 2: Сервис `sout_declaration.py` (проекция + render)

**Files:**
- Create: `backend/app/services/sout_declaration.py`
- Test: `backend/tests/test_sout_declaration_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_declaration_service.py
"""Тесты чистой проекции декларации (без БД)."""
from types import SimpleNamespace

from app.services.sout_declaration import build_declaration_projection


def _wp(code="РМ-01", cls="acceptable", person_id=None):
    return SimpleNamespace(
        id=code, workplace_code=code, position_name="Слесарь",
        assessed_class=cls, person_id=person_id,
    )


def _factor(cls="acceptable"):
    return SimpleNamespace(code=None, name="x", measured_class=cls)


def test_projection_marks_eligible_and_ineligible() -> None:
    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="СОУТ", report_number="N1", report_date=None),
        workplaces_with_factors=[
            (_wp(code="РМ-01", cls="acceptable", person_id="p1"), []),
            (_wp(code="РМ-02", cls="harmful_3_1"), [_factor("harmful_3_1")]),
            (_wp(code="РМ-03", cls="acceptable"), [_factor("harmful_3_2")]),
        ],
    )
    by_code = {r.workplace_code: r for r in rows}
    assert by_code["РМ-01"].eligible is True
    assert by_code["РМ-01"].headcount == "1"        # person_id задан
    assert by_code["РМ-02"].eligible is False        # класс 3.1
    assert by_code["РМ-03"].eligible is False        # класс 2, но фактор 3.1
    assert by_code["РМ-03"].headcount == "—"         # person_id нет


def test_projection_report_ref_built_from_campaign() -> None:
    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="СОУТ", report_number="N1", report_date="2026-06-01"),
        workplaces_with_factors=[(_wp(), [])],
    )
    assert rows[0].report_ref == "N1 от 2026-06-01"


def test_projection_coerces_enum_class_value() -> None:
    enum_like = SimpleNamespace(value="optimal")
    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="x", report_number=None, report_date=None),
        workplaces_with_factors=[(_wp(cls=enum_like), [])],
    )
    assert rows[0].assessed_class == "optimal"
    assert rows[0].eligible is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.sout_declaration`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/sout_declaration.py
"""Рендер декларации соответствия условий труда: БД → DOCX/PDF.

Зеркало services/sout_print.py. Переиспользует RenderedDoc / PdfRendererUnavailable
/ _to_pdf / helpers из sout_print (один контур СОУТ — DRY)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sout import declaration as decl
from app.domains.sout.print_form import SoutCardFactorRow
from app.models.sout import SoutWorkplace
from app.models.tenanting import Tenant
from app.services.sout_print import (
    _DOCX_MEDIA,
    _iso,
    _load_campaign,
    _load_factors,
    _org_header,
    _raw,
    _to_pdf,
    PdfRendererUnavailable,  # noqa: F401  (re-export for route import symmetry)
    RenderedDoc,
)


def _report_ref(campaign) -> str | None:
    parts = [
        getattr(campaign, "report_number", None),
        f"от {_iso(getattr(campaign, 'report_date', None))}"
        if getattr(campaign, "report_date", None)
        else None,
    ]
    joined = " ".join(p for p in parts if p)
    return joined or None


def build_declaration_projection(*, campaign, workplaces_with_factors) -> list[decl.DeclarationRow]:
    """Чистая сборка строк декларации (тестируется без БД)."""
    ref = _report_ref(campaign)
    rows: list[decl.DeclarationRow] = []
    for wp, factors in workplaces_with_factors:
        card_factors = [
            SoutCardFactorRow(code=f.code, name=f.name, measured_class=_raw(f.measured_class))
            for f in factors
        ]
        assessed = _raw(wp.assessed_class)
        eligible, reason = decl.evaluate_eligibility(assessed, card_factors)
        rows.append(
            decl.DeclarationRow(
                workplace_code=wp.workplace_code,
                position_name=wp.position_name,
                assessed_class=assessed,
                headcount="1" if getattr(wp, "person_id", None) else "—",
                report_ref=ref,
                eligible=eligible,
                ineligible_reason=reason,
            )
        )
    return rows


async def _load_workplaces(session: AsyncSession, tenant: Tenant, cid: str) -> list[SoutWorkplace]:
    return list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        ).scalars().all()
    )


async def render_declaration(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    workplaces = await _load_workplaces(session, tenant, campaign_id)
    pairs = [(wp, await _load_factors(session, tenant, wp.id)) for wp in workplaces]
    all_rows = build_declaration_projection(campaign=campaign, workplaces_with_factors=pairs)
    data = decl.DeclarationPrintData(
        org_header=_org_header(tenant),
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        campaign_name=campaign.name,
        report_number=getattr(campaign, "report_number", None),
        report_date=_iso(getattr(campaign, "report_date", None)),
        rows=[r for r in all_rows if r.eligible],  # печать — только подлежащие
    )
    docx_bytes = decl.build_declaration_docx(data)
    base_name = "sout-declaration"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration_service.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sout_declaration.py backend/tests/test_sout_declaration_service.py
git commit -m "feat(sout): declaration projection + render service (срез-4)"
```

---

## Task 3: Схемы `DeclarationRowRead` + `DeclarationPreview`

**Files:**
- Modify: `backend/app/schemas/sout.py` (добавить в конец)

- [ ] **Step 1: Write the failing test**

Добавить в `backend/tests/test_sout_declaration_service.py`:

```python
def test_declaration_schema_validates_from_dataclass() -> None:
    from app.schemas.sout import DeclarationRowRead

    rows = build_declaration_projection(
        campaign=SimpleNamespace(name="x", report_number=None, report_date=None),
        workplaces_with_factors=[(_wp(person_id="p1"), [])],
    )
    read = DeclarationRowRead.model_validate(rows[0], from_attributes=True)
    assert read.workplace_code == "РМ-01"
    assert read.eligible is True
    assert read.headcount == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration_service.py::test_declaration_schema_validates_from_dataclass -q`
Expected: FAIL — `ImportError: cannot import name 'DeclarationRowRead'`

- [ ] **Step 3: Write minimal implementation**

Добавить в конец `backend/app/schemas/sout.py`:

```python
# --- Declaration of conformity (срез-4) ---
class DeclarationRowRead(BaseSchema):
    workplace_code: str
    position_name: str
    assessed_class: str | None
    headcount: str
    report_ref: str | None
    eligible: bool
    ineligible_reason: str | None


class DeclarationPreview(BaseSchema):
    campaign_id: str
    campaign_name: str
    eligible: list[DeclarationRowRead]
    ineligible: list[DeclarationRowRead]
    eligible_count: int
    ineligible_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration_service.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/sout.py backend/tests/test_sout_declaration_service.py
git commit -m "feat(sout): declaration preview schemas (срез-4)"
```

---

## Task 4: Эндпоинты preview + print

**Files:**
- Modify: `backend/app/api/routes/sout.py`
- Test: `backend/tests/test_sout_declaration_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_declaration_api.py
"""API-контракт декларации СОУТ (monkeypatch как test_sout_print_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.services.sout_print import PdfRendererUnavailable, RenderedDoc

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


@pytest.mark.asyncio
async def test_declaration_print_docx_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "render_declaration",
        AsyncMock(return_value=RenderedDoc(content=b"DOCX", filename="sout-declaration.docx", media_type=_DOCX)),
    )
    resp = await routes.print_declaration(
        cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
    )
    assert resp.status_code == 200
    assert resp.media_type == _DOCX


@pytest.mark.asyncio
async def test_declaration_print_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_declaration", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.print_declaration(
            cid="missing", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_declaration_print_503_when_pdf_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_declaration", AsyncMock(side_effect=PdfRendererUnavailable("no soffice")))
    with pytest.raises(Exception) as exc:
        await routes.print_declaration(
            cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="pdf",
        )
    assert getattr(exc.value, "status_code", None) == 503


@pytest.mark.asyncio
async def test_declaration_preview_splits_eligible(monkeypatch):
    from app.domains.sout.declaration import DeclarationRow

    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_campaign", AsyncMock(return_value=SimpleNamespace(
        id="c1", name="СОУТ 2026", report_number="N1", report_date=None)))
    monkeypatch.setattr(routes, "_load_declaration_pairs", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "build_declaration_projection", lambda **k: [
        DeclarationRow("РМ-01", "Слесарь", "acceptable", "1", "N1", True, None),
        DeclarationRow("РМ-02", "Сварщик", "harmful_3_1", "—", "N1", False, "класс 3.1 — вредные/опасные условия"),
    ])
    out = await routes.get_declaration(
        cid="c1", tenant=_tenant(), session=AsyncMock(), access=None,
    )
    assert out.eligible_count == 1 and out.ineligible_count == 1
    assert out.eligible[0].workplace_code == "РМ-01"
    assert out.ineligible[0].ineligible_reason is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration_api.py -q`
Expected: FAIL — `AttributeError: module 'app.api.routes.sout' has no attribute 'print_declaration'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/routes/sout.py`, add imports near the other service/schema imports:

```python
from app.services.sout_declaration import (
    build_declaration_projection,
    render_declaration,
)
```

and extend the `app.schemas.sout` import block with:

```python
    DeclarationPreview,
    DeclarationRowRead,
```

Add a shared pairs-loader after `_load_medical_inputs` (so API + tests can patch it):

```python
async def _load_declaration_pairs(session: AsyncSession, tenant: Tenant, cid: str):
    """[(workplace, [factors]), ...] for the campaign, ordered by code."""
    workplaces = list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        ).scalars().all()
    )
    pairs = []
    for w in workplaces:
        factors = list(
            (
                await session.execute(
                    select(SoutFactor).where(
                        SoutFactor.workplace_id == w.id, SoutFactor.tenant_id == tenant.id
                    )
                )
            ).scalars().all()
        )
        pairs.append((w, factors))
    return pairs
```

Add the two endpoints after `print_summary_sheet` (end of file):

```python
@router.get("/{cid}/declaration", response_model=DeclarationPreview)
async def get_declaration(
    cid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> DeclarationPreview:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    campaign = await _get_campaign(session, tenant, cid)
    pairs = await _load_declaration_pairs(session, tenant, cid)
    rows = build_declaration_projection(campaign=campaign, workplaces_with_factors=pairs)
    eligible = [DeclarationRowRead.model_validate(r, from_attributes=True) for r in rows if r.eligible]
    ineligible = [DeclarationRowRead.model_validate(r, from_attributes=True) for r in rows if not r.eligible]
    return DeclarationPreview(
        campaign_id=cid,
        campaign_name=campaign.name,
        eligible=eligible,
        ineligible=ineligible,
        eligible_count=len(eligible),
        ineligible_count=len(ineligible),
    )


@router.get("/{cid}/declaration/print")
async def print_declaration(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        rendered = await render_declaration(session, tenant=tenant, campaign_id=cid, fmt=fmt)
    except PdfRendererUnavailable as exc:
        raise _pdf_unavailable() from exc
    if rendered is None:
        raise _not_found("Campaign")
    return _doc_response(rendered)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration_api.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full СОУТ cohort to confirm no regression**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration.py tests/test_sout_declaration_service.py tests/test_sout_declaration_api.py tests/test_sout_print_api.py tests/test_sout_api.py -q`
Expected: PASS (EXIT 0)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/sout.py backend/tests/test_sout_declaration_api.py
git commit -m "feat(sout): declaration preview + print endpoints (срез-4)"
```

---

## Task 5: Фронт — API + секция «Декларация соответствия»

**Files:**
- Modify: `frontend/src/api/sout.ts`
- Modify: `frontend/src/pages/sout/SoutPage.tsx`
- Test: `frontend/src/__tests__/SoutDeclaration.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SoutDeclaration.test.tsx
import { describe, expect, it, vi, beforeEach } from "vitest";

import { soutApi } from "@/api/sout";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn() },
}));

describe("soutApi declaration methods", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("getDeclaration calls the preview endpoint", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { campaign_id: "c1", campaign_name: "СОУТ", eligible: [], ineligible: [], eligible_count: 0, ineligible_count: 0 },
    });

    const out = await soutApi.getDeclaration("c1");

    expect(apiClient.get).toHaveBeenCalledWith("/sout/c1/declaration");
    expect(out.campaign_id).toBe("c1");
  });

  it("downloadDeclaration requests blob with format param", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: new Blob(["x"]) });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await soutApi.downloadDeclaration("c1", "pdf");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/sout/c1/declaration/print",
      expect.objectContaining({ params: { format: "pdf" }, responseType: "blob" }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/SoutDeclaration.test.tsx`
Expected: FAIL — `soutApi.getDeclaration is not a function`

- [ ] **Step 3: Write minimal implementation (api)**

Add interfaces after `NormSuggestions` in `frontend/src/api/sout.ts`:

```typescript
export interface SoutDeclarationRow {
  workplace_code: string;
  position_name: string;
  assessed_class: string | null;
  headcount: string;
  report_ref: string | null;
  eligible: boolean;
  ineligible_reason: string | null;
}

export interface SoutDeclarationPreview {
  campaign_id: string;
  campaign_name: string;
  eligible: SoutDeclarationRow[];
  ineligible: SoutDeclarationRow[];
  eligible_count: number;
  ineligible_count: number;
}
```

Add methods inside `soutApi` (after `downloadSummary`):

```typescript
  async getDeclaration(campaignId: string): Promise<SoutDeclarationPreview> {
    return (await apiClient.get<SoutDeclarationPreview>(`${base}/${campaignId}/declaration`)).data;
  },

  async downloadDeclaration(campaignId: string, fmt: "docx" | "pdf", nameHint?: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${base}/${campaignId}/declaration/print`, {
      params: { format: fmt },
      responseType: "blob",
    });
    downloadBlob(data, `sout-declaration-${nameHint ?? campaignId}.${fmt}`);
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/SoutDeclaration.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Wire the UI section into ReportPanel**

In `frontend/src/pages/sout/SoutPage.tsx`, add to the `soutApi` import usage a lazy declaration block. Inside `ReportPanel`, after the existing state, add:

```tsx
  const [declaration, setDeclaration] = useState<SoutDeclarationPreview | null>(null);

  useEffect(() => {
    let active = true;
    void soutApi
      .getDeclaration(campaign.id)
      .then((d) => { if (active) setDeclaration(d); })
      .catch(() => { if (active) setDeclaration(null); });
    return () => { active = false; };
  }, [campaign.id]);

  const handleDeclarationDownload = async (fmt: "docx" | "pdf") => {
    try {
      await soutApi.downloadDeclaration(campaign.id, fmt, campaign.name);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      toast.error(
        fmt === "pdf" && status === 503
          ? "PDF-конвертер недоступен, скачайте DOCX"
          : "Не удалось скачать документ",
      );
    }
  };
```

Import the type at the top (extend the existing `@/api/sout` import):

```tsx
import { soutApi, type SoutCampaign, type SoutCampaignReport, type SoutDeclarationPreview } from "@/api/sout";
```

(Match the actual existing import shape in the file; add only `SoutDeclarationPreview` if the others are already imported.)

Add the buttons next to the «Сводная» buttons in the header `<span className="flex gap-1">`:

```tsx
            <Button type="button" size="sm" variant="outline"
              onClick={() => void handleDeclarationDownload("docx")}>
              Декларация DOCX
            </Button>
            <Button type="button" size="sm" variant="outline"
              onClick={() => void handleDeclarationDownload("pdf")}>
              Декларация PDF
            </Button>
```

Add a summary line inside `<CardContent>` (before the workplaces list block):

```tsx
        {declaration !== null ? (
          <div className="rounded-md border border-border p-3 text-sm" data-testid="sout-declaration-summary">
            <p className="font-medium">Декларация соответствия (класс 1-2)</p>
            <p className="text-muted-foreground">
              Подлежат декларированию: {declaration.eligible_count} · не подлежат: {declaration.ineligible_count}
            </p>
            {declaration.ineligible.length > 0 ? (
              <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">
                {declaration.ineligible.map((r) => (
                  <li key={r.workplace_code}>
                    {r.workplace_code} · {r.position_name} — {r.ineligible_reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
```

- [ ] **Step 6: Verify frontend gates**

Run: `cd frontend && npx vitest run src/__tests__/SoutDeclaration.test.tsx && npx tsc --noEmit && npx eslint src/api/sout.ts src/pages/sout/SoutPage.tsx --max-warnings=0`
Expected: vitest PASS, tsc clean, eslint 0 errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/sout.ts frontend/src/pages/sout/SoutPage.tsx frontend/src/__tests__/SoutDeclaration.test.tsx
git commit -m "feat(sout): declaration UI section + api methods (срез-4)"
```

---

## Task 6: Верификация + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху)

- [ ] **Step 1: Backend cohort + migration-absence proof**

Run:
```
cd backend && .venv\Scripts\python -m pytest tests/test_sout_declaration.py tests/test_sout_declaration_service.py tests/test_sout_declaration_api.py tests/test_sout_print_form.py tests/test_sout_print_api.py tests/test_sout_print_service.py tests/test_sout_api.py tests/test_sout_service.py tests/test_sout_models.py tests/test_sout_schemas.py -q
```
Expected: EXIT 0.

Run (migration dividend proof — must be empty):
```
git diff --name-only origin/main...HEAD -- backend/app/migrations/versions/
```
Expected: пусто (ни одного файла).

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`
Expected: EXIT 0.

- [ ] **Step 3: Write handoff block**

Prepend a `## Last Agent Handoff (2026-06-28, СОУТ срез-4 декларация соответствия ...)` section to `AI_IMPLEMENTATION_REPORT.md` summarizing: 3-layer mirror, no-migration dividend (proven), eligibility rule (класс 1-2 И 0 вредных), placeholders for employer requisites, test counts, deferred items, branch `feat/sout-srez4-declaration-p10-04`, merge=user's call.

- [ ] **Step 4: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs: handoff for СОУТ срез-4 декларация соответствия"
```

---

## Self-Review (выполнено при написании плана)

- **Spec coverage:** домен/eligibility (T1), сервис/проекция+render (T2), схемы (T3), preview+print эндпоинты (T4), фронт api+UI (T5), отложенное — не реализуется (документировано). Все разделы спеки покрыты.
- **No migration:** доказывается шагом T6.1 (`git diff` по migrations/versions пуст).
- **Type consistency:** `DeclarationRow`(domain) ↔ `DeclarationRowRead`(schema) — одинаковый набор полей (`from_attributes`); `build_declaration_projection`/`render_declaration`/`evaluate_eligibility`/`build_declaration_docx` — имена согласованы между T1/T2/T4 и тестами; `_to_pdf`/`_load_factors`/`_load_campaign`/`_raw`/`_iso`/`_org_header`/`_DOCX_MEDIA` импортируются из `sout_print` (существуют).
- **Анти-грабли:** класс-2-но-фактор-3.1 кейс есть и в домен-юнитах (T1), и в проекции (T2).
