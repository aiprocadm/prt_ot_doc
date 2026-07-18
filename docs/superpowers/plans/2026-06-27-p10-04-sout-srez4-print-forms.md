# СОУТ срез-4а — печатные формы (Карта СОУТ + Сводная ведомость) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать результаты СОУТ выгружаемыми в DOCX/PDF — Карта СОУТ (на рабочее место) и Сводная ведомость (на кампанию), зеркаля 3-слойный паттерн печати медосмотров 29н.

**Architecture:** Чистый сборщик (`domains/sout/print_form.py`, python-docx, без I/O) → сервис-обёртка (`services/sout_print.py`: async-загрузка + чистая сборка PrintData + опц. PDF) → два GET-эндпоинта в `api/routes/sout.py` (`?format=docx|pdf`). Источник данных — те же ORM-строки, что и `build_report()`; миграций нет.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / python-docx / LibreOffice (PDF); React/TypeScript / Vitest (фронт).

**Спека:** `docs/superpowers/specs/2026-06-27-p10-04-sout-srez4-print-forms-design.md`

**Ветка:** `feat/sout-srez4-print-forms-p10-04` (от `origin/main` @ `f72871b6`).

**Запуск тестов (Win/.venv, summary теряется — судим по EXIT):**
```
cd backend; ../.venv/Scripts/python.exe -m pytest tests/<файл> -q > out.txt 2>&1; echo "EXIT=$LASTEXITCODE"
```
Канон Py3.12 PG CI = финальный гейт.

---

### Task 1: Чистый сборщик DOCX — `domains/sout/print_form.py`

**Files:**
- Create: `backend/app/domains/sout/print_form.py`
- Test: `backend/tests/test_sout_print_form.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_print_form.py
"""Юниты чистого сборщика печатных форм СОУТ (без БД, без async)."""
from io import BytesIO

from docx import Document

from app.domains.sout.print_form import (
    SoutCardFactorRow,
    SoutCardGuaranteeRow,
    SoutCardPrintData,
    SoutSummaryPrintData,
    SoutSummaryRow,
    build_summary_sheet_docx,
    build_sout_card_docx,
    class_counts,
    harmful_factor_count,
)


def _text(docx_bytes: bytes) -> str:
    doc = Document(BytesIO(docx_bytes))
    parts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _card(**over) -> SoutCardPrintData:
    base = dict(
        org_header="ООО Ромашка",
        generated_at="2026-06-27",
        expert_org_name="ЭкспертОрг",
        report_number="СОУТ-1",
        report_date="2026-06-01",
        workplace_code="РМ-01",
        position_name="Сварщик",
        assessed_class="harmful_3_2",
        assessment_date="2026-05-20",
        next_assessment_date="2031-05-20",
        factors=[SoutCardFactorRow(code="4.50", name="Шум", measured_class="harmful_3_1")],
        guarantees=[SoutCardGuaranteeRow(kind="milk", detail="0.5 л/смена")],
    )
    base.update(over)
    return SoutCardPrintData(**base)


def test_card_contains_identity_and_class_labels() -> None:
    out = build_sout_card_docx(_card())
    txt = _text(out)
    assert "РМ-01" in txt and "Сварщик" in txt
    assert "ЭкспертОрг" in txt
    assert "3.2" in txt          # итоговый класс РМ (RU-метка)
    assert "Шум" in txt and "3.1" in txt
    assert "Молоко" in txt       # GUARANTEE_KIND_LABELS["milk"]


def test_card_empty_sections_render() -> None:
    out = build_sout_card_docx(_card(factors=[], guarantees=[], assessed_class=None))
    txt = _text(out)
    assert "РМ-01" in txt
    assert "—" in txt            # отсутствующий класс / пустые секции


def test_harmful_factor_count_counts_3_1_and_above() -> None:
    rows = [
        SoutCardFactorRow(code=None, name="a", measured_class="acceptable"),
        SoutCardFactorRow(code=None, name="b", measured_class="harmful_3_1"),
        SoutCardFactorRow(code=None, name="c", measured_class="dangerous"),
        SoutCardFactorRow(code=None, name="d", measured_class=None),
    ]
    assert harmful_factor_count(rows) == 2


def test_class_counts_canonical_order_and_tally() -> None:
    counts = class_counts(["optimal", "harmful_3_1", "harmful_3_1", None, "dangerous"])
    as_dict = dict(counts)
    assert as_dict["3.1"] == 2
    assert as_dict["4 (опасный)"] == 1
    # канонический порядок: оптимальный раньше опасного
    labels = [label for label, _ in counts]
    assert labels.index("1 (оптимальный)") < labels.index("4 (опасный)")


def test_summary_lists_workplaces_and_stats() -> None:
    data = SoutSummaryPrintData(
        org_header="ООО Ромашка",
        generated_at="2026-06-27",
        campaign_name="СОУТ 2026",
        expert_org_name="ЭкспертОрг",
        report_number="СОУТ-1",
        report_date="2026-06-01",
        rows=[
            SoutSummaryRow(
                workplace_code="РМ-01", position_name="Сварщик",
                assessed_class="harmful_3_2", harmful_factor_count=2,
                next_assessment_date="2031-05-20",
            ),
            SoutSummaryRow(
                workplace_code="РМ-02", position_name="Слесарь",
                assessed_class="acceptable", harmful_factor_count=0,
                next_assessment_date=None,
            ),
        ],
        class_counts=class_counts(["harmful_3_2", "acceptable"]),
    )
    txt = _text(build_summary_sheet_docx(data))
    assert "РМ-01" in txt and "РМ-02" in txt
    assert "Сварщик" in txt and "Слесарь" in txt
    assert "СОУТ 2026" in txt


def test_summary_empty_campaign_renders() -> None:
    data = SoutSummaryPrintData(
        org_header="ООО Ромашка", generated_at="2026-06-27",
        campaign_name="Пустая", expert_org_name=None,
        report_number=None, report_date=None, rows=[], class_counts=[],
    )
    txt = _text(build_summary_sheet_docx(data))
    assert "Пустая" in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_form.py -q`
Expected: FAIL — `ModuleNotFoundError: app.domains.sout.print_form`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domains/sout/print_form.py
"""Чистый сборщик печатных форм СОУТ: Карта СОУТ + Сводная ведомость.

Без sqlalchemy / без I/O — как domains/medical/print_form.py. Принимает уже
собранный снимок (*PrintData), возвращает байты DOCX. RU-метки классов/гарантий
и канонический порядок классов — локальные константы (модуль не зависит ни от
ORM, ни от фронта)."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

from docx import Document

# --- RU vocab + канонический порядок классов (локально для чистого модуля) ---
SOUT_CLASS_LABELS = {
    "optimal": "1 (оптимальный)",
    "acceptable": "2 (допустимый)",
    "harmful_3_1": "3.1",
    "harmful_3_2": "3.2",
    "harmful_3_3": "3.3",
    "harmful_3_4": "3.4",
    "dangerous": "4 (опасный)",
}
# Канонический порядок (метки заголовков + порядок статистики берут отсюда).
SOUT_CLASS_ORDER = (
    "optimal", "acceptable", "harmful_3_1", "harmful_3_2",
    "harmful_3_3", "harmful_3_4", "dangerous",
)
# Вредные/опасные классы (3.1 и выше) — для подсчёта «вредных факторов».
HARMFUL_CLASSES = frozenset(
    {"harmful_3_1", "harmful_3_2", "harmful_3_3", "harmful_3_4", "dangerous"}
)
GUARANTEE_KIND_LABELS = {
    "additional_leave": "Дополнительный отпуск",
    "extra_pay": "Повышенная оплата труда",
    "reduced_hours": "Сокращённая рабочая неделя",
    "milk": "Молоко / лечебно-профилактическое питание",
    "early_pension": "Досрочная пенсия",
    "medical_exam": "Обязательный медосмотр",
}


def class_label(code: str | None) -> str:
    if code is None:
        return "—"
    return SOUT_CLASS_LABELS.get(code, code)


def guarantee_label(code: str) -> str:
    return GUARANTEE_KIND_LABELS.get(code, code)


@dataclass
class SoutCardFactorRow:
    code: str | None
    name: str
    measured_class: str | None  # raw enum value


@dataclass
class SoutCardGuaranteeRow:
    kind: str  # raw enum value
    detail: str | None


@dataclass
class SoutCardPrintData:
    org_header: str
    generated_at: str | None
    expert_org_name: str | None
    report_number: str | None
    report_date: str | None
    workplace_code: str
    position_name: str
    assessed_class: str | None
    assessment_date: str | None
    next_assessment_date: str | None
    factors: list[SoutCardFactorRow] = field(default_factory=list)
    guarantees: list[SoutCardGuaranteeRow] = field(default_factory=list)


@dataclass
class SoutSummaryRow:
    workplace_code: str
    position_name: str
    assessed_class: str | None
    harmful_factor_count: int
    next_assessment_date: str | None


@dataclass
class SoutSummaryPrintData:
    org_header: str
    generated_at: str | None
    campaign_name: str
    expert_org_name: str | None
    report_number: str | None
    report_date: str | None
    rows: list[SoutSummaryRow] = field(default_factory=list)
    class_counts: list[tuple[str, int]] = field(default_factory=list)  # (label, count)


def harmful_factor_count(factors: list[SoutCardFactorRow]) -> int:
    """Число факторов с классом 3.1+ (по measured_class фактора, не итоговому классу РМ)."""
    return sum(1 for f in factors if f.measured_class in HARMFUL_CLASSES)


def class_counts(assessed_classes: list[str | None]) -> list[tuple[str, int]]:
    """Статистика РМ по классам в каноническом порядке (только классы с count > 0)."""
    tally: dict[str, int] = {}
    for code in assessed_classes:
        if code is None:
            continue
        tally[code] = tally.get(code, 0) + 1
    return [
        (SOUT_CLASS_LABELS.get(code, code), tally[code])
        for code in SOUT_CLASS_ORDER
        if code in tally
    ]


def _kv(doc, label: str, value: str | None) -> None:
    doc.add_paragraph(f"{label}: {value if value is not None else '—'}")


def build_sout_card_docx(data: SoutCardPrintData) -> bytes:
    doc = Document()
    doc.add_heading("Карта специальной оценки условий труда", level=0)
    _kv(doc, "Организация", data.org_header)
    _kv(doc, "Экспертная организация", data.expert_org_name)
    _kv(doc, "Отчёт №", data.report_number)
    _kv(doc, "Дата отчёта", data.report_date)
    _kv(doc, "Код рабочего места", data.workplace_code)
    _kv(doc, "Должность", data.position_name)
    _kv(doc, "Итоговый класс условий труда", class_label(data.assessed_class))
    _kv(doc, "Дата оценки", data.assessment_date)
    _kv(doc, "Дата следующей оценки", data.next_assessment_date)

    doc.add_heading("Вредные и (или) опасные производственные факторы", level=1)
    if data.factors:
        tbl = doc.add_table(rows=1, cols=4)
        tbl.style = "Table Grid"
        for i, title in enumerate(["№", "Код (29н)", "Наименование фактора", "Класс"]):
            tbl.rows[0].cells[i].text = title
        for idx, f in enumerate(data.factors, start=1):
            cells = tbl.add_row().cells
            cells[0].text = str(idx)
            cells[1].text = f.code or "—"
            cells[2].text = f.name
            cells[3].text = class_label(f.measured_class)
    else:
        doc.add_paragraph("—")

    doc.add_heading("Гарантии и компенсации", level=1)
    if data.guarantees:
        for g in data.guarantees:
            detail = f": {g.detail}" if g.detail else ""
            doc.add_paragraph(f"• {guarantee_label(g.kind)}{detail}")
    else:
        doc.add_paragraph("—")

    doc.add_heading("Комиссия по проведению СОУТ", level=1)
    doc.add_paragraph("Председатель комиссии: ____________________ / ____________________")
    doc.add_paragraph("Члены комиссии: ____________________ / ____________________")
    _kv(doc, "Дата формирования", data.generated_at)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_summary_sheet_docx(data: SoutSummaryPrintData) -> bytes:
    doc = Document()
    doc.add_heading("Сводная ведомость результатов СОУТ", level=0)
    _kv(doc, "Организация", data.org_header)
    _kv(doc, "Кампания", data.campaign_name)
    _kv(doc, "Экспертная организация", data.expert_org_name)
    _kv(doc, "Отчёт №", data.report_number)
    _kv(doc, "Дата отчёта", data.report_date)

    if data.rows:
        tbl = doc.add_table(rows=1, cols=6)
        tbl.style = "Table Grid"
        for i, title in enumerate(
            ["№", "Код РМ", "Должность", "Итоговый класс", "Вредных факторов", "След. оценка"]
        ):
            tbl.rows[0].cells[i].text = title
        for idx, r in enumerate(data.rows, start=1):
            cells = tbl.add_row().cells
            cells[0].text = str(idx)
            cells[1].text = r.workplace_code
            cells[2].text = r.position_name
            cells[3].text = class_label(r.assessed_class)
            cells[4].text = str(r.harmful_factor_count)
            cells[5].text = r.next_assessment_date or "—"
    else:
        doc.add_paragraph("—")

    doc.add_heading("Итоги по классам условий труда", level=1)
    if data.class_counts:
        for label, count in data.class_counts:
            doc.add_paragraph(f"Класс {label}: {count}")
    else:
        doc.add_paragraph("—")
    _kv(doc, "Дата формирования", data.generated_at)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_form.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/sout/print_form.py backend/tests/test_sout_print_form.py
git commit -m "feat(sout): pure DOCX builder for Карта СОУТ + Сводная ведомость (срез-4а)"
```

---

### Task 2: Сервис-обёртка — `services/sout_print.py`

Чистая сборка PrintData (`_card_print_data`/`_summary_print_data`) из ORM-строк тестируется без БД; async-загрузчики + PDF-конвертер тонкие.

**Files:**
- Create: `backend/app/services/sout_print.py`
- Test: `backend/tests/test_sout_print_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_print_service.py
"""Тесты сборки PrintData в sout_print (чистые части, без БД)."""
from types import SimpleNamespace

from app.services.sout_print import _card_print_data, _summary_print_data


def _wp(**over):
    base = dict(
        id="w1", workplace_code="РМ-01", position_name="Сварщик",
        assessed_class="harmful_3_2", assessment_date=None, next_assessment_date=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _factor(name="Шум", code="4.50", cls="harmful_3_1"):
    return SimpleNamespace(code=code, name=name, measured_class=cls)


def _guarantee(kind="milk", detail=None):
    return SimpleNamespace(kind=kind, detail=detail)


def test_card_print_data_maps_rows() -> None:
    data = _card_print_data(
        org_header="ООО Ромашка",
        generated_at="2026-06-27",
        campaign=SimpleNamespace(expert_org_name="Эксп", report_number="N1", report_date=None),
        workplace=_wp(),
        factors=[_factor()],
        guarantees=[_guarantee()],
    )
    assert data.workplace_code == "РМ-01"
    assert data.expert_org_name == "Эксп"
    assert data.assessed_class == "harmful_3_2"
    assert len(data.factors) == 1 and data.factors[0].name == "Шум"
    assert data.guarantees[0].kind == "milk"


def test_summary_print_data_counts_harmful_and_classes() -> None:
    data = _summary_print_data(
        org_header="ООО Ромашка",
        generated_at="2026-06-27",
        campaign=SimpleNamespace(name="СОУТ 2026", expert_org_name=None, report_number=None, report_date=None),
        workplaces_with_factors=[
            (_wp(workplace_code="РМ-01", assessed_class="harmful_3_2"),
             [_factor(cls="harmful_3_1"), _factor(cls="acceptable")]),
            (_wp(workplace_code="РМ-02", assessed_class="acceptable"), []),
        ],
    )
    assert [r.workplace_code for r in data.rows] == ["РМ-01", "РМ-02"]
    assert data.rows[0].harmful_factor_count == 1   # один фактор 3.1
    assert dict(data.class_counts)["3.2"] == 1
    assert dict(data.class_counts)["2 (допустимый)"] == 1


def test_class_enums_coerced_to_raw_value() -> None:
    # measured_class может прийти как enum-объект с .value — сборка берёт .value/str
    enum_like = SimpleNamespace(value="dangerous")
    data = _card_print_data(
        org_header="o", generated_at=None,
        campaign=SimpleNamespace(expert_org_name=None, report_number=None, report_date=None),
        workplace=_wp(assessed_class=enum_like),
        factors=[], guarantees=[],
    )
    assert data.assessed_class == "dangerous"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.sout_print`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/sout_print.py
"""Рендер печатных форм СОУТ (Карта СОУТ + Сводная ведомость): БД → DOCX/PDF.

Зеркало services/medical_print.py: tenant-scoped загрузка → чистая сборка снимка
→ python-docx сборщик → опц. PDF через LibreOffice. RenderedDoc /
PdfRendererUnavailable объявлены локально (модуль не зависит от medical/work_permits)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sout import print_form as pf
from app.models.sout import SoutCampaign, SoutFactor, SoutGuarantee, SoutWorkplace
from app.models.tenanting import Tenant

logger = logging.getLogger(__name__)

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MEDIA = "application/pdf"
_PDF_TIMEOUT_S = 45


class PdfRendererUnavailable(Exception):
    """LibreOffice недоступен/таймаут (роут → 503)."""


@dataclass
class RenderedDoc:
    content: bytes
    filename: str
    media_type: str


def _raw(value) -> str | None:
    """Enum-объект (.value) либо строка → raw-строка; None пропускает."""
    if value is None:
        return None
    return getattr(value, "value", value)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _org_header(tenant: Tenant) -> str:
    return getattr(tenant, "name", None) or getattr(tenant, "slug", "")


# --- чистая сборка снимков (тестируется без БД) ---
def _card_print_data(
    *, org_header, generated_at, campaign, workplace, factors, guarantees
) -> pf.SoutCardPrintData:
    return pf.SoutCardPrintData(
        org_header=org_header,
        generated_at=generated_at,
        expert_org_name=getattr(campaign, "expert_org_name", None),
        report_number=getattr(campaign, "report_number", None),
        report_date=_iso(getattr(campaign, "report_date", None)) or getattr(campaign, "report_date", None),
        workplace_code=workplace.workplace_code,
        position_name=workplace.position_name,
        assessed_class=_raw(workplace.assessed_class),
        assessment_date=_iso(getattr(workplace, "assessment_date", None)),
        next_assessment_date=_iso(getattr(workplace, "next_assessment_date", None)),
        factors=[
            pf.SoutCardFactorRow(code=f.code, name=f.name, measured_class=_raw(f.measured_class))
            for f in factors
        ],
        guarantees=[
            pf.SoutCardGuaranteeRow(kind=_raw(g.kind), detail=g.detail) for g in guarantees
        ],
    )


def _summary_print_data(
    *, org_header, generated_at, campaign, workplaces_with_factors
) -> pf.SoutSummaryPrintData:
    rows = []
    for wp, factors in workplaces_with_factors:
        card_factors = [
            pf.SoutCardFactorRow(code=f.code, name=f.name, measured_class=_raw(f.measured_class))
            for f in factors
        ]
        rows.append(
            pf.SoutSummaryRow(
                workplace_code=wp.workplace_code,
                position_name=wp.position_name,
                assessed_class=_raw(wp.assessed_class),
                harmful_factor_count=pf.harmful_factor_count(card_factors),
                next_assessment_date=_iso(getattr(wp, "next_assessment_date", None)),
            )
        )
    counts = pf.class_counts([_raw(wp.assessed_class) for wp, _ in workplaces_with_factors])
    return pf.SoutSummaryPrintData(
        org_header=org_header,
        generated_at=generated_at,
        campaign_name=campaign.name,
        expert_org_name=getattr(campaign, "expert_org_name", None),
        report_number=getattr(campaign, "report_number", None),
        report_date=_iso(getattr(campaign, "report_date", None)) or getattr(campaign, "report_date", None),
        rows=rows,
        class_counts=counts,
    )


async def _to_pdf(docx_bytes: bytes, *, base_name: str) -> RenderedDoc:
    try:
        from app.modules.pdf.convert import convert_docx_bytes
        from app.modules.pdf.service_pool import LibreOfficePool

        pdf_bytes, _sha = await asyncio.to_thread(
            convert_docx_bytes,
            source_bytes=docx_bytes,
            timeout_s=_PDF_TIMEOUT_S,
            pool=LibreOfficePool(),
            passport=None,
        )
    except Exception as exc:
        logger.warning("sout print: PDF conversion failed: %s", exc, exc_info=True)
        raise PdfRendererUnavailable(str(exc)) from exc
    return RenderedDoc(content=pdf_bytes, filename=f"{base_name}.pdf", media_type=_PDF_MEDIA)


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


async def _load_campaign(session: AsyncSession, tenant: Tenant, cid: str) -> SoutCampaign | None:
    return (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.id == cid,
                SoutCampaign.tenant_id == tenant.id,
                SoutCampaign.deleted_at.is_(None),
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


async def _load_guarantees(session: AsyncSession, tenant: Tenant, wid: str):
    return list(
        (
            await session.execute(
                select(SoutGuarantee).where(
                    SoutGuarantee.workplace_id == wid, SoutGuarantee.tenant_id == tenant.id
                )
            )
        ).scalars().all()
    )


async def render_sout_card(
    session: AsyncSession, *, tenant: Tenant, workplace_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    wp = await _load_workplace(session, tenant, workplace_id)
    if wp is None:
        return None
    campaign = await _load_campaign(session, tenant, wp.campaign_id)
    factors = await _load_factors(session, tenant, workplace_id)
    guarantees = await _load_guarantees(session, tenant, workplace_id)
    data = _card_print_data(
        org_header=_org_header(tenant),
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        campaign=campaign or SoutCampaign(),
        workplace=wp,
        factors=factors,
        guarantees=guarantees,
    )
    docx_bytes = pf.build_sout_card_docx(data)
    base_name = f"sout-card-{wp.workplace_code}"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)


async def render_summary_sheet(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    workplaces = list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == campaign_id,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        ).scalars().all()
    )
    pairs = [(wp, await _load_factors(session, tenant, wp.id)) for wp in workplaces]
    data = _summary_print_data(
        org_header=_org_header(tenant),
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        campaign=campaign,
        workplaces_with_factors=pairs,
    )
    docx_bytes = pf.build_summary_sheet_docx(data)
    base_name = "sout-summary"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sout_print.py backend/tests/test_sout_print_service.py
git commit -m "feat(sout): print service — tenant-scoped DOCX/PDF render for Карта/Сводная (срез-4а)"
```

---

### Task 3: Эндпоинты печати в `api/routes/sout.py`

**Files:**
- Modify: `backend/app/api/routes/sout.py` (импорты + 2 эндпоинта + хелпер `_render_to_response`)
- Test: `backend/tests/test_sout_print_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_print_api.py
"""API-контракт печатных форм СОУТ (monkeypatch как test_sout_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.services.sout_print import PdfRendererUnavailable, RenderedDoc

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


@pytest.mark.asyncio
async def test_card_print_docx_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "render_sout_card",
        AsyncMock(return_value=RenderedDoc(content=b"DOCX", filename="sout-card-РМ-01.docx", media_type=_DOCX)),
    )
    resp = await routes.print_sout_card(
        wid="w1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
    )
    assert resp.status_code == 200
    assert resp.media_type == _DOCX
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_card_print_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_sout_card", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.print_sout_card(
            wid="missing", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_card_print_503_when_pdf_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_sout_card", AsyncMock(side_effect=PdfRendererUnavailable("no soffice")))
    with pytest.raises(Exception) as exc:
        await routes.print_sout_card(
            wid="w1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="pdf",
        )
    assert getattr(exc.value, "status_code", None) == 503


@pytest.mark.asyncio
async def test_summary_print_docx_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "render_summary_sheet",
        AsyncMock(return_value=RenderedDoc(content=b"DOCX", filename="sout-summary.docx", media_type=_DOCX)),
    )
    resp = await routes.print_summary_sheet(
        cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
    )
    assert resp.status_code == 200
    assert resp.media_type == _DOCX


@pytest.mark.asyncio
async def test_summary_print_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_summary_sheet", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.print_summary_sheet(
            cid="missing", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
        )
    assert getattr(exc.value, "status_code", None) == 404
```

> Note: невалидный `format` (422) обеспечивается `Literal["docx","pdf"]` на уровне FastAPI-валидации запроса — проверяется интеграционно через TestClient в существующих сборках, здесь юнит-уровень вызывает функции напрямую, поэтому 422-кейс не входит в этот файл (Literal не достижим прямым вызовом).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_api.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'print_sout_card'`.

- [ ] **Step 3: Write minimal implementation**

В `backend/app/api/routes/sout.py`:

1) Добавь импорты (рядом с прочими `from app...`):

```python
from urllib.parse import quote

from fastapi import Response  # уже импортирован — не дублировать
from typing import Literal     # добавить Literal к существующему `from typing import Annotated`

from app.services.sout_print import (
    PdfRendererUnavailable,
    RenderedDoc,
    render_sout_card,
    render_summary_sheet,
)
```

> Приведи `from typing import Annotated` к `from typing import Annotated, Literal`. `Response`, `Query`, `status`, `HTTPException` уже импортированы из fastapi (строка 6).

2) Добавь хелпер и два эндпоинта в конец файла (после `get_report`):

```python
# --- Printable forms (срез-4а) ---
def _pdf_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=api_problem_detail(
            code="SOUT_PDF_RENDERER_UNAVAILABLE",
            message="PDF converter is unavailable",
            error_type="sout",
        ),
    )


def _doc_response(rendered: RenderedDoc) -> Response:
    encoded_name = quote(rendered.filename, safe="")
    return Response(
        content=rendered.content,
        media_type=rendered.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/workplaces/{wid}/card/print")
async def print_sout_card(
    wid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        rendered = await render_sout_card(session, tenant=tenant, workplace_id=wid, fmt=fmt)
    except PdfRendererUnavailable as exc:
        raise _pdf_unavailable() from exc
    if rendered is None:
        raise _not_found("Workplace")
    return _doc_response(rendered)


@router.get("/{cid}/summary/print")
async def print_summary_sheet(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        rendered = await render_summary_sheet(session, tenant=tenant, campaign_id=cid, fmt=fmt)
    except PdfRendererUnavailable as exc:
        raise _pdf_unavailable() from exc
    if rendered is None:
        raise _not_found("Campaign")
    return _doc_response(rendered)
```

> ВНИМАНИЕ к порядку маршрутов: `/{cid}/summary/print` идёт ПОСЛЕ существующего `/{cid}/report` и не конфликтует (разные хвосты). `/workplaces/{wid}/card/print` не пересекается с `/workplaces/{wid}` (GET без хвоста) и `/workplaces/{wid}/norm-suggestions`. FastAPI матчит по полному пути — порядок добавления здесь некритичен, но держим оба в конце файла.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_api.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run smoke import + regression of SOUT cohort**

Run:
```
cd backend; ../.venv/Scripts/python.exe -c "import app.api.routes.sout"
../.venv/Scripts/python.exe -m pytest tests/test_sout_api.py tests/test_sout_print_form.py tests/test_sout_print_service.py tests/test_sout_print_api.py -q
```
Expected: import EXIT 0; все тесты PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/sout.py backend/tests/test_sout_print_api.py
git commit -m "feat(sout): GET card/summary print endpoints (?format=docx|pdf, 503/404) (срез-4а)"
```

---

### Task 4: Фронтенд — API-методы + кнопки скачивания

**Files:**
- Modify: `frontend/src/api/sout.ts` (2 метода в `soutApi`)
- Modify: `frontend/src/pages/sout/SoutPage.tsx` (кнопки в `ReportPanel`)
- Test: `frontend/src/__tests__/SoutPrintButtons.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SoutPrintButtons.test.tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { soutApi } from "@/api/sout";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn() },
}));

describe("soutApi print download methods", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("downloadSummary requests blob with format param", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: new Blob(["x"]) });
    const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await soutApi.downloadSummary("c1", "pdf");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/sout/c1/summary/print",
      expect.objectContaining({ params: { format: "pdf" }, responseType: "blob" }),
    );
    createUrl.mockRestore();
  });

  it("downloadCard requests blob for workplace", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: new Blob(["x"]) });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await soutApi.downloadCard("w1", "docx", "РМ-01");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/sout/workplaces/w1/card/print",
      expect.objectContaining({ params: { format: "docx" }, responseType: "blob" }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/__tests__/SoutPrintButtons.test.tsx`
Expected: FAIL — `soutApi.downloadSummary is not a function`.

- [ ] **Step 3: Write minimal implementation**

В `frontend/src/api/sout.ts` добавь в объект `soutApi` (после `linkFactorHazard`), используя существующий `downloadBlob`:

```typescript
  async downloadCard(workplaceId: string, fmt: "docx" | "pdf", nameHint?: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${base}/workplaces/${workplaceId}/card/print`, {
      params: { format: fmt },
      responseType: "blob",
    });
    downloadBlob(data, `sout-card-${nameHint ?? workplaceId}.${fmt}`);
  },

  async downloadSummary(campaignId: string, fmt: "docx" | "pdf", nameHint?: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${base}/${campaignId}/summary/print`, {
      params: { format: fmt },
      responseType: "blob",
    });
    downloadBlob(data, `sout-summary-${nameHint ?? campaignId}.${fmt}`);
  },
```

И добавь импорт вверху файла:

```typescript
import { downloadBlob } from "@/utils/download";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend; npx vitest run src/__tests__/SoutPrintButtons.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Add buttons to SoutPage ReportPanel**

В `frontend/src/pages/sout/SoutPage.tsx`:

(a) В заголовке `ReportPanel` (рядом с `CardTitle`, внутри `CardHeader` строки 344-346) добавь кнопки сводной ведомости:

```tsx
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Рабочие места — {campaign.name}</CardTitle>
          <span className="flex gap-1">
            <Button type="button" size="sm" variant="outline"
              onClick={() => void soutApi.downloadSummary(campaign.id, "docx", campaign.name)}>
              Сводная DOCX
            </Button>
            <Button type="button" size="sm" variant="outline"
              onClick={() => void soutApi.downloadSummary(campaign.id, "pdf", campaign.name)}>
              PDF
            </Button>
          </span>
        </div>
      </CardHeader>
```

(b) В строке РМ (внутри `<div className="flex items-center justify-between gap-2">` со строки 357, рядом с бейджами) добавь кнопку карты per-workplace:

```tsx
                  <span className="flex items-center gap-2">
                    <Badge variant="secondary">{classLabel(workplace.assessed_class)}</Badge>
                    {workplace.is_reassessment_due ? (
                      <Badge variant="destructive" className="text-xs">Переоценка просрочена</Badge>
                    ) : null}
                    <Button type="button" size="sm" variant="outline"
                      onClick={() => void soutApi.downloadCard(workplace.id, "docx", workplace.workplace_code)}>
                      Карта DOCX
                    </Button>
                    <Button type="button" size="sm" variant="outline"
                      onClick={() => void soutApi.downloadCard(workplace.id, "pdf", workplace.workplace_code)}>
                      PDF
                    </Button>
                  </span>
```

> `Button` уже импортирован в SoutPage (используется в `LinkInput`). Проверь, что импорт присутствует вверху файла.

- [ ] **Step 6: Verify build + typecheck + lint**

Run:
```
cd frontend; npx vitest run src/__tests__/SoutPrintButtons.test.tsx
npx tsc --noEmit
npx eslint src/api/sout.ts src/pages/sout/SoutPage.tsx --max-warnings=0
npm run build
```
Expected: vitest PASS, tsc 0, eslint 0, build EXIT 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/sout.ts frontend/src/pages/sout/SoutPage.tsx frontend/src/__tests__/SoutPrintButtons.test.tsx
git commit -m "feat(sout): frontend download buttons for Карта СОУТ + Сводная ведомость (срез-4а)"
```

---

### Task 5: Верификация контура + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новая секция handoff сверху)

- [ ] **Step 1: Backend cohort regression**

Run:
```
cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_sout_print_form.py tests/test_sout_print_service.py tests/test_sout_print_api.py tests/test_sout_api.py tests/test_sout_service.py tests/test_sout_suggestions.py tests/test_medical_print_form.py -q > sout_srez4_out.txt 2>&1; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0. (Включён medical print-form-тест — проверяет, что зеркалирование паттерна не задело медицину.)

- [ ] **Step 2: Confirm NO migration in diff**

Run: `git diff --name-only origin/main...HEAD`
Expected: НЕТ файлов под `backend/alembic/` или `migrations/`. Если есть — стоп, что-то не так (дивиденд без миграции нарушен).

- [ ] **Step 3: Frontend full check**

Run:
```
cd frontend; npx tsc --noEmit; npx eslint src/api/sout.ts src/pages/sout/SoutPage.tsx --max-warnings=0; npm run build
```
Expected: tsc 0, eslint 0, build EXIT 0.

- [ ] **Step 4: Write handoff section**

Добавь секцию в начало `AI_IMPLEMENTATION_REPORT.md` (после строки 1 `# AI Implementation Report`) по образцу существующих handoff-секций: дата, контур «СОУТ срез-4а», ветка, что построено (5 задач), дивиденд без миграции, тесты (EXIT-коды), отложенное (декларация/импорт/реквизиты комиссии/letterhead/ZIP), Next (merge=пользователя).

- [ ] **Step 5: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(sout): срез-4а handoff — печатные формы Карта СОУТ + Сводная ведомость"
```

---

## Self-Review (заполнено автором плана)

**Spec coverage:**
- Слой 1 чистый сборщик → Task 1 ✓; Слой 2 сервис → Task 2 ✓; Слой 3 эндпоинты → Task 3 ✓; фронт → Task 4 ✓; тесты во всех; отложенное в handoff Task 5 ✓.
- Карта: идентификация/факторы/класс/гарантии/даты/подписи → builder Task 1 ✓.
- Сводная: таблица + статистика классов + harmful_count → Task 1/2 ✓.
- 503/404/Content-Disposition/Literal-422 → Task 3 ✓.

**Placeholder scan:** код полный во всех шагах; плейсхолдеров/опечаток нет.

**Type consistency:** `SoutCardPrintData`/`SoutSummaryPrintData`/`SoutCardFactorRow`/`SoutCardGuaranteeRow`/`SoutSummaryRow` едины в Task 1↔2; `RenderedDoc`/`PdfRendererUnavailable`/`render_sout_card`/`render_summary_sheet` едины в Task 2↔3; `downloadCard`/`downloadSummary` едины в Task 4. Канонический порядок классов — одна константа `SOUT_CLASS_ORDER`. Предикат «вредный» — `HARMFUL_CLASSES` (одна константа, используется и в `harmful_factor_count`).
