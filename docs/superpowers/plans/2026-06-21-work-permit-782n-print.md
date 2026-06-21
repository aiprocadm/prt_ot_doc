# Наряд-допуск 782н Ф4 «печатный бланк» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Печатный бланк наряда-допуска 782н (DOCX, опц. PDF, опц. фирменный бланк) с блоком подписей ПЭП (ФИО/дата/режим/хэш).

**Architecture:** Чистый сборщик `build_work_permit_docx` (python-docx, без I/O) ← сервис `render_work_permit` (загрузка наряда+связей+подписей, резолв ФИО, обёртка бланком и PDF) ← синхронный эндпоинт `GET /work-permits/{id}/print?format=`. Переиспользует готовый движок печати (`apply_headers_to_docx`, `convert_docx_bytes`).

**Tech Stack:** Python/FastAPI, python-docx (через зависимость docxtpl), `modules/pdf` (LibreOffice), `modules/branding`/`modules/headers` (letterhead), React/Vite (фронт).

**Среда выполнения:** Windows, рабочая директория `D:\Кодинг\Создание платформы по ОТ`. Python — `.venv\Scripts\python.exe` (локально Py3.13.7; канон CI — Py3.12.12, расхождение версии отмечать, не прерываться). pytest через PowerShell→файл, итог по EXIT-коду; **foreground, не в фоне** (фоновый шелл может умереть до конца прогона). Ветка `feat/work-permits-782n-print` (стек поверх Ф3b — уже создана). Спека: `docs/superpowers/specs/2026-06-21-work-permit-782n-print-design.md`.

**Грабля тест-фабрики (из Ф3b):** `data_factory.create_person()` по умолчанию даёт компанию «ACME Corp», у `company` UNIQUE `(tenant_id, name)` → две дефолтных персоны в одном тенанте = IntegrityError. Создавать ОДИН tenant+company и переиспускать (`create_person(tenant=t, company=c, first_name=...)`); персон создавать ДО открытия тестовой сессии (паттерн `tests/test_work_permit_signing.py`).

---

### Task 1: Чистый сборщик DOCX (`print_form.py`)

**Files:**
- Create: `backend/app/domains/work_permits/print_form.py`
- Test: `tests/test_work_permit_print_form.py`

Чистый модуль (без sqlalchemy/I/O, как `lifecycle.py`): датаклассы снимка + RU-словари + сборка DOCX через python-docx.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_work_permit_print_form.py
"""Ф4 чистый сборщик DOCX наряда-допуска: открыть результат python-docx и проверить содержимое."""
from __future__ import annotations

from io import BytesIO

from docx import Document

from app.domains.work_permits.print_form import (
    SignatureLine, WorkPermitPrintData, build_work_permit_docx,
)


def _all_text(doc_bytes: bytes) -> str:
    doc = Document(BytesIO(doc_bytes))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def _sample() -> WorkPermitPrintData:
    return WorkPermitPrintData(
        number="НД-7", work_type_label="Работа на высоте", status_label="Выдан",
        org_header="ООО Ромашка", subdivision="Цех №1",
        planned_start="2026-06-20 08:00", planned_end="2026-06-20 18:00",
        zone_text="фасад корпуса А", content_text="монтаж", conditions_text="ясно",
        equipment_text="люлька", hazards_text="высота 12 м",
        safety_systems_labels=["Удерживающие", "Страховочные"],
        measures_before="ограждение", measures_during="наблюдение",
        special_conditions="—", ppe_text="каска, строп",
        members=[("Производитель работ", "Иванов И.И."), ("Допускающий", "Петров П.П.")],
        briefing={"conducted_by_fio": "Иванов И.И.", "conducted_at": "2026-06-20 07:45", "topics": "ТБ на высоте"},
        daily_admissions=[{"date": "2026-06-20", "start": "08:00", "end": "18:00", "admitted_by_fio": "Петров П.П."}],
        extensions=[{"old_end": "2026-06-20 18:00", "new_end": "2026-06-21 18:00", "at": "2026-06-20 17:30"}],
        completion={"text": "работы окончены, место сдано", "recorded_at": "2026-06-21 17:00"},
        closed_at="2026-06-21 17:05",
        signatures=[
            SignatureLine(group="permit", role_label="Производитель работ", fio="Иванов И.И.",
                          status_label="Подписано", signed_at="2026-06-20 08:05", mode="attested",
                          hash_short="a1b2c3d4e5f6a7b8"),
            SignatureLine(group="closing", role_label="Сдал", fio="Иванов И.И.",
                          status_label="Подписано", signed_at="2026-06-21 17:00", mode="attested",
                          hash_short="ffeeddccbbaa9988"),
        ],
    )


def test_build_docx_contains_core_fields():
    text = _all_text(build_work_permit_docx(_sample()))
    assert "НД-7" in text
    assert "Иванов И.И." in text
    assert "Удерживающие" in text          # метка системы безопасности
    assert "работы окончены, место сдано" in text
    assert "a1b2c3d4e5f6a7b8" in text       # хэш ПЭП в блоке подписей
    assert "Сдал" in text                    # роль закрытия


def test_build_docx_empty_sections_do_not_crash():
    data = WorkPermitPrintData(
        number="НД-8", work_type_label="Работа на высоте", status_label="Черновик",
        org_header="ООО Ромашка", subdivision=None, planned_start=None, planned_end=None,
        zone_text="зона", content_text=None, conditions_text=None, equipment_text=None,
        hazards_text=None, safety_systems_labels=[], measures_before=None, measures_during=None,
        special_conditions=None, ppe_text=None, members=[], briefing=None,
        daily_admissions=[], extensions=[], completion=None, closed_at=None, signatures=[],
    )
    out = build_work_permit_docx(data)  # не должно бросать
    assert isinstance(out, bytes) and len(out) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run (PowerShell): `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_form.py -p no:cacheprovider 2>&1 | Select-Object -Last 6; echo "EXIT=$LASTEXITCODE"`
Expected: FAIL (ModuleNotFoundError: print_form).

- [ ] **Step 3: Implement `print_form.py`**

```python
# backend/app/domains/work_permits/print_form.py
"""Ф4: чистый сборщик печатного бланка наряда-допуска 782н (python-docx).

Без sqlalchemy / без I/O — как domains/work_permits/lifecycle.py. Принимает уже
собранный снимок (WorkPermitPrintData), возвращает байты DOCX. RU-метки —
локальные словари (модуль не зависит от фронта)."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from docx import Document

# --- RU vocab (зеркало lib/workPermitVocab.ts, но локально для чистого модуля) ---
WORK_TYPE_LABELS = {
    "hot_work": "Огневые работы", "gas_hazardous": "Газоопасные работы",
    "height": "Работа на высоте", "confined_space": "Работа в замкнутом пространстве",
    "excavation": "Земляные работы", "electrical": "Электротехнические работы",
}
MEMBER_ROLE_LABELS = {
    "issuer": "Выдающий наряд", "supervisor": "Ответственный руководитель",
    "admitter": "Допускающий", "foreman": "Производитель работ",
    "observer": "Наблюдающий", "member": "Член бригады",
}
SAFETY_SYSTEM_LABELS = {
    "restraint": "Удерживающие", "positioning": "Позиционирования",
    "fall_arrest": "Страховочные", "rescue_evacuation": "Для эвакуации и спасения",
    "access": "Для подъёма и спуска",
}
STATUS_LABELS = {
    "draft": "Черновик", "issued": "Выдан", "suspended": "Приостановлен",
    "closed": "Закрыт", "cancelled": "Отменён",
}
SIGN_GROUP_LABELS = {"permit": "Наряд", "briefing": "Целевой инструктаж", "closing": "Закрытие"}


def work_type_label(code: str) -> str:
    return WORK_TYPE_LABELS.get(code, code)


def member_role_label(code: str) -> str:
    return MEMBER_ROLE_LABELS.get(code, code)


def safety_system_label(code: str) -> str:
    return SAFETY_SYSTEM_LABELS.get(code, code)


def status_label(code: str) -> str:
    return STATUS_LABELS.get(code, code)


@dataclass
class SignatureLine:
    group: str          # "permit" | "briefing" | "closing"
    role_label: str
    fio: str
    status_label: str
    signed_at: str | None
    mode: str           # "attested" | "code" | "—"
    hash_short: str


@dataclass
class WorkPermitPrintData:
    number: str
    work_type_label: str
    status_label: str
    org_header: str
    subdivision: str | None
    planned_start: str | None
    planned_end: str | None
    zone_text: str
    content_text: str | None
    conditions_text: str | None
    equipment_text: str | None
    hazards_text: str | None
    safety_systems_labels: list[str]
    measures_before: str | None
    measures_during: str | None
    special_conditions: str | None
    ppe_text: str | None
    members: list[tuple[str, str]]          # (role_label, fio)
    briefing: dict | None                    # {conducted_by_fio, conducted_at, topics}
    daily_admissions: list[dict]             # [{date, start, end, admitted_by_fio}]
    extensions: list[dict]                   # [{old_end, new_end, at}]
    completion: dict | None                  # {text, recorded_at}
    closed_at: str | None
    signatures: list[SignatureLine]


def _kv(doc, label: str, value: str | None) -> None:
    doc.add_paragraph(f"{label}: {value if value else '—'}")


def build_work_permit_docx(data: WorkPermitPrintData) -> bytes:
    doc = Document()
    doc.add_heading(
        "НАРЯД-ДОПУСК на производство работ повышенной опасности "
        "(работа на высоте, Приказ Минтруда № 782н)", level=0,
    )

    # 1. Шапка
    _kv(doc, "Организация", data.org_header)
    _kv(doc, "Подразделение", data.subdivision)
    _kv(doc, "Номер наряда", data.number)
    _kv(doc, "Вид работ", data.work_type_label)
    _kv(doc, "Статус", data.status_label)
    _kv(doc, "Плановое начало", data.planned_start)
    _kv(doc, "Плановое окончание", data.planned_end)

    # 2. Ответственные и бригада
    doc.add_heading("Ответственные лица и состав бригады", level=1)
    if data.members:
        tbl = doc.add_table(rows=1, cols=2)
        tbl.style = "Table Grid"
        hdr = tbl.rows[0].cells
        hdr[0].text, hdr[1].text = "Роль", "Ф.И.О."
        for role_label, fio in data.members:
            cells = tbl.add_row().cells
            cells[0].text, cells[1].text = role_label, fio
    else:
        doc.add_paragraph("—")

    # 3. Описание работ
    doc.add_heading("Описание работ", level=1)
    _kv(doc, "Место (зона)", data.zone_text)
    _kv(doc, "Содержание работ", data.content_text)
    _kv(doc, "Условия проведения", data.conditions_text)
    _kv(doc, "Оборудование", data.equipment_text)
    _kv(doc, "Опасные факторы", data.hazards_text)
    _kv(doc, "Системы обеспечения безопасности",
        ", ".join(data.safety_systems_labels) if data.safety_systems_labels else None)
    _kv(doc, "Мероприятия до начала работ", data.measures_before)
    _kv(doc, "Мероприятия в процессе работ", data.measures_during)
    _kv(doc, "Особые условия", data.special_conditions)
    _kv(doc, "Средства индивидуальной защиты", data.ppe_text)

    # 4. Целевой инструктаж
    doc.add_heading("Целевой инструктаж", level=1)
    if data.briefing:
        _kv(doc, "Провёл", data.briefing.get("conducted_by_fio"))
        _kv(doc, "Дата", data.briefing.get("conducted_at"))
        _kv(doc, "Темы", data.briefing.get("topics"))
    else:
        doc.add_paragraph("—")

    # 5. Ежедневный допуск
    doc.add_heading("Ежедневный допуск к работе", level=1)
    if data.daily_admissions:
        tbl = doc.add_table(rows=1, cols=4)
        tbl.style = "Table Grid"
        hdr = tbl.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Дата", "Начало", "Окончание", "Допустил"
        for a in data.daily_admissions:
            cells = tbl.add_row().cells
            cells[0].text = str(a.get("date") or "")
            cells[1].text = str(a.get("start") or "")
            cells[2].text = str(a.get("end") or "")
            cells[3].text = str(a.get("admitted_by_fio") or "")
    else:
        doc.add_paragraph("—")

    # 6. Продления
    doc.add_heading("Продления наряда", level=1)
    if data.extensions:
        for e in data.extensions:
            doc.add_paragraph(
                f"Продлён с {e.get('old_end') or '—'} до {e.get('new_end') or '—'} "
                f"({e.get('at') or '—'})"
            )
    else:
        doc.add_paragraph("—")

    # 7. Окончание и закрытие
    doc.add_heading("Окончание работ и закрытие наряда", level=1)
    if data.completion:
        _kv(doc, "Акт окончания работ", data.completion.get("text"))
        _kv(doc, "Дата оформления", data.completion.get("recorded_at"))
    else:
        doc.add_paragraph("Акт окончания не оформлен")
    _kv(doc, "Наряд закрыт", data.closed_at)

    # 8. Подписи ПЭП
    doc.add_heading("Подписи (простая электронная подпись)", level=1)
    if data.signatures:
        tbl = doc.add_table(rows=1, cols=6)
        tbl.style = "Table Grid"
        hdr = tbl.rows[0].cells
        for i, title in enumerate(["Раздел", "Ф.И.О.", "Статус", "Дата", "Режим", "Хэш ПЭП"]):
            hdr[i].text = title
        for s in data.signatures:
            cells = tbl.add_row().cells
            cells[0].text = f"{SIGN_GROUP_LABELS.get(s.group, s.group)} · {s.role_label}"
            cells[1].text = s.fio
            cells[2].text = s.status_label
            cells[3].text = s.signed_at or "—"
            cells[4].text = s.mode
            cells[5].text = s.hash_short
    else:
        doc.add_paragraph("Подписи отсутствуют")

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_form.py -p no:cacheprovider 2>&1 | Select-Object -Last 6; echo "EXIT=$LASTEXITCODE"`
Expected: EXIT=0, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/print_form.py tests/test_work_permit_print_form.py
git commit -m "feat(work-permits): чистый сборщик DOCX печатного бланка 782н (Ф4)"
```

---

### Task 2: Сервис загрузки и обёртки (`work_permit_print.py`)

**Files:**
- Create: `backend/app/services/work_permit_print.py`
- Test: `tests/test_work_permit_print_service.py`

Загружает наряд+связи+подписи, резолвит ФИО, собирает `WorkPermitPrintData`, зовёт сборщик, опц. бланк, опц. PDF.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_work_permit_print_service.py
"""Ф4 сервис рендера наряда: собирает данные из БД и отдаёт DOCX-байты."""
from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc
from app.domains.work_permits.signing import sign_closing
from app.services.work_permit_print import PdfRendererUnavailable, render_work_permit


async def _persons(data_factory, *names):
    tenant = await data_factory.ensure_tenant()
    company = await data_factory.create_company(tenant=tenant)
    people = []
    for i, nm in enumerate(names):
        people.append(await data_factory.create_person(
            tenant=tenant, company=company, first_name=nm, last_name=f"P{i}"))
    return tenant, people


def _docx_text(b: bytes) -> str:
    doc = Document(BytesIO(b))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                parts.append(c.text)
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_render_docx_includes_members_and_signature(sessionmaker, data_factory):
    tenant, (foreman, supervisor) = await _persons(data_factory, "Ivan", "Petr")
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(session, tenant_id=tid, work_type="height",
                                          zone_text="фасад", number="НД-7")
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=foreman.id, role="foreman")
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=supervisor.id, role="supervisor")
        wp.status = lc.STATUS_ISSUED
        await session.flush()
        await svc.record_completion(session, tenant_id=tid, work_permit_id=wp.id,
                                    completion_text="работы окончены", actor_user_id="u1")
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=foreman.id, mode="attested", requested_by="u1")
        rendered = await render_work_permit(session, tenant=tenant, permit_id=wp.id,
                                            fmt="docx", with_letterhead=False)
        assert rendered.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert rendered.filename.endswith(".docx")
        text = _docx_text(rendered.content)
        assert "НД-7" in text
        assert "Ivan" in text                  # ФИО члена бригады зарезолвлено
        assert "работы окончены" in text


@pytest.mark.asyncio
async def test_render_unknown_permit_returns_none(sessionmaker, data_factory):
    tenant, _ = await _persons(data_factory, "Solo")
    async with sessionmaker() as session:
        rendered = await render_work_permit(session, tenant=tenant, permit_id="missing-id",
                                            fmt="docx", with_letterhead=False)
        assert rendered is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_service.py -p no:cacheprovider 2>&1 | Select-Object -Last 6; echo "EXIT=$LASTEXITCODE"`
Expected: FAIL (ModuleNotFoundError: work_permit_print).

- [ ] **Step 3: Implement `work_permit_print.py`**

```python
# backend/app/services/work_permit_print.py
"""Ф4: загрузка наряда+связей+подписей, сборка печатного снимка, опц. бланк и PDF."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import print_form as pf
from app.models.models import Person, SignatureRequest, Tenant
from app.models.work_permit import (
    WorkPermit, WorkPermitBriefing, WorkPermitDailyAdmission, WorkPermitEvent, WorkPermitMember,
)

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


def _fmt_dt(value) -> str | None:
    return value.isoformat(sep=" ", timespec="minutes") if value else None


def _closing_kind_label(role: str | None) -> str:
    kind = lc.role_to_closing_kind(role) if role else None
    return {"handover": "Сдал", "acceptance": "Принял"}.get(kind, role or "—")


async def _name_map(session: AsyncSession, tenant_id: str, person_ids: set[str]) -> dict[str, str]:
    ids = {p for p in person_ids if p}
    if not ids:
        return {}
    rows = (await session.execute(
        select(Person).where(Person.tenant_id == tenant_id, Person.id.in_(tuple(ids)))
    )).scalars().all()
    out: dict[str, str] = {}
    for p in rows:
        out[str(p.id)] = " ".join(x for x in [p.last_name, p.first_name, getattr(p, "middle_name", None) or ""] if x).strip()
    return out


async def render_work_permit(
    session: AsyncSession, *, tenant: Tenant, permit_id: str,
    fmt: str = "docx", with_letterhead: bool = True,
) -> RenderedDoc | None:
    tid = str(tenant.id)
    wp = (await session.execute(
        select(WorkPermit).where(WorkPermit.id == permit_id, WorkPermit.tenant_id == tid)
    )).scalar_one_or_none()
    if wp is None:
        return None

    members = (await session.execute(
        select(WorkPermitMember).where(
            WorkPermitMember.tenant_id == tid, WorkPermitMember.work_permit_id == permit_id
        ).order_by(WorkPermitMember.created_at.asc())
    )).scalars().all()
    briefings = (await session.execute(
        select(WorkPermitBriefing).where(
            WorkPermitBriefing.tenant_id == tid, WorkPermitBriefing.work_permit_id == permit_id
        ).order_by(WorkPermitBriefing.created_at.asc())
    )).scalars().all()
    admissions = (await session.execute(
        select(WorkPermitDailyAdmission).where(
            WorkPermitDailyAdmission.tenant_id == tid, WorkPermitDailyAdmission.work_permit_id == permit_id
        ).order_by(WorkPermitDailyAdmission.admission_date.asc())
    )).scalars().all()
    ext_events = (await session.execute(
        select(WorkPermitEvent).where(
            WorkPermitEvent.tenant_id == tid, WorkPermitEvent.work_permit_id == permit_id,
            WorkPermitEvent.event_type == "extended",
        ).order_by(WorkPermitEvent.at.asc())
    )).scalars().all()
    briefing_ids = [b.id for b in briefings]
    sig_object_ids = [permit_id] + briefing_ids
    signatures = (await session.execute(
        select(SignatureRequest).where(
            SignatureRequest.tenant_id == tid,
            SignatureRequest.object_type.in_(("work_permit", "work_permit_briefing", "work_permit_closing")),
            SignatureRequest.object_id.in_(tuple(sig_object_ids)),
        ).order_by(SignatureRequest.created_at.asc())
    )).scalars().all()

    member_role_by_person = {str(m.person_id): m.role for m in members}
    person_ids = {str(m.person_id) for m in members}
    person_ids |= {str(b.conducted_by_person_id) for b in briefings if b.conducted_by_person_id}
    person_ids |= {str(a.admitted_by_person_id) for a in admissions if a.admitted_by_person_id}
    person_ids |= {str(s.signer_person_id) for s in signatures if s.signer_person_id}
    names = await _name_map(session, tid, person_ids)

    def fio(pid) -> str:
        return names.get(str(pid), "—") if pid else "—"

    # подписи → строки
    briefing_id_set = set(briefing_ids)
    sig_lines: list[pf.SignatureLine] = []
    for s in signatures:
        if s.object_type == "work_permit_closing":
            group = "closing"
            role_label = _closing_kind_label(member_role_by_person.get(str(s.signer_person_id)))
        elif s.object_type == "work_permit_briefing":
            group = "briefing"
            role_label = pf.member_role_label(member_role_by_person.get(str(s.signer_person_id), ""))
        else:
            group = "permit"
            role_label = pf.member_role_label(member_role_by_person.get(str(s.signer_person_id), ""))
        signer = fio(s.signer_person_id) if s.signer_person_id else (s.signer_name or "—")
        mode = "code" if s.confirm_code_hash else "attested"
        sig_lines.append(pf.SignatureLine(
            group=group, role_label=role_label, fio=signer,
            status_label="Подписано" if s.status == "signed" else (s.status or "—"),
            signed_at=_fmt_dt(s.signed_at), mode=mode,
            hash_short=(s.content_hash[:16] if s.content_hash else "—"),
        ))

    briefing0 = briefings[0] if briefings else None
    data = pf.WorkPermitPrintData(
        number=wp.number or str(wp.id), work_type_label=pf.work_type_label(wp.work_type),
        status_label=pf.status_label(str(wp.status)), org_header=tenant.name or tenant.slug,
        subdivision=wp.subdivision_text, planned_start=_fmt_dt(wp.planned_start),
        planned_end=_fmt_dt(wp.planned_end), zone_text=wp.zone_text, content_text=wp.content_text,
        conditions_text=wp.conditions_text, equipment_text=wp.equipment_text, hazards_text=wp.hazards_text,
        safety_systems_labels=[pf.safety_system_label(c) for c in (wp.safety_systems or [])],
        measures_before=wp.measures_before_text, measures_during=wp.measures_during_text,
        special_conditions=wp.special_conditions_text, ppe_text=wp.ppe_text,
        members=[(pf.member_role_label(m.role), fio(m.person_id)) for m in members],
        briefing=({"conducted_by_fio": fio(briefing0.conducted_by_person_id),
                   "conducted_at": _fmt_dt(briefing0.conducted_at),
                   "topics": briefing0.topics_text} if briefing0 else None),
        daily_admissions=[{"date": a.admission_date.isoformat() if a.admission_date else "",
                           "start": _fmt_dt(a.start_at), "end": _fmt_dt(a.end_at),
                           "admitted_by_fio": fio(a.admitted_by_person_id)} for a in admissions],
        extensions=[{"old_end": (e.meta or {}).get("old_end"), "new_end": (e.meta or {}).get("new_end"),
                     "at": _fmt_dt(e.at)} for e in ext_events],
        completion=({"text": wp.completion_text, "recorded_at": _fmt_dt(wp.completion_recorded_at)}
                    if wp.completion_text else None),
        closed_at=_fmt_dt(wp.closed_at), signatures=sig_lines,
    )

    docx_bytes = pf.build_work_permit_docx(data)

    if with_letterhead and getattr(settings, "doc_pipeline_letterhead_auto", False):
        try:
            from app.modules.branding.letterhead import IssuerRef, LetterheadResolver
            from app.modules.branding.service import BrandingService
            from app.modules.headers.engine import apply_headers_to_docx
            resolver = LetterheadResolver(BrandingService(session, tenant))
            decision = await resolver.resolve(
                issuer=IssuerRef(kind="company", company_id=None),
                site_id=str(wp.site_id) if wp.site_id else None,
                doc={"title": f"Наряд-допуск {data.number}"}, override=None,
            )
            if decision.apply:
                docx_bytes, _report = apply_headers_to_docx(
                    docx_bytes=docx_bytes, preset=decision.preset,
                    context=decision.header_context, watermark_override=decision.watermark,
                )
        except Exception:  # best-effort: бланк не должен ронять печать
            pass

    base_name = f"work-permit-{(wp.number or wp.id)}"
    if fmt == "pdf":
        try:
            from app.modules.pdf.convert import convert_docx_bytes
            from app.modules.pdf.service_pool import LibreOfficePool
            pdf_bytes, _sha = convert_docx_bytes(
                source_bytes=docx_bytes, timeout_s=_PDF_TIMEOUT_S, pool=LibreOfficePool(), passport=None,
            )
        except Exception as exc:  # soffice отсутствует / таймаут / сбой конвертации
            raise PdfRendererUnavailable(str(exc)) from exc
        return RenderedDoc(content=pdf_bytes, filename=f"{base_name}.pdf", media_type=_PDF_MEDIA)

    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
```

> NB реализатору: сверь имена полей `Person` (`middle_name`), `IssuerRef`/`LetterheadResolver.resolve` сигнатуру и `LetterheadDecision` (`apply`/`preset`/`header_context`/`watermark`) по `backend/app/modules/branding/letterhead.py` и образцу `backend/app/tasks/_core.py:357-382`. Если `IssuerRef(kind="company", company_id=None)` требует непустой company_id — резолвь company наряда (через site→company или tenant default) или ставь `with_letterhead=False` по умолчанию в эндпоинте и доведи бланк отдельным шагом. Бланк обёрнут в `try/except` — его сбой не валит печать (best-effort по спеке §10).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_service.py -p no:cacheprovider 2>&1 | Select-Object -Last 8; echo "EXIT=$LASTEXITCODE"`
Expected: EXIT=0, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/work_permit_print.py tests/test_work_permit_print_service.py
git commit -m "feat(work-permits): сервис рендера печатного наряда (данные+бланк+PDF) (Ф4)"
```

---

### Task 3: API эндпоинт печати

**Files:**
- Modify: `backend/app/api/routes/work_permits.py` (добавить эндпоинт в конец, рядом с прочими)
- Test: `tests/api/test_work_permit_print_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_work_permit_print_api.py
"""Ф4 API печати наряда: DOCX 200 + заголовки; cross-tenant 404; невалидный формат 422."""
from __future__ import annotations

import pytest

from app.models.enums import RoleEnum

BASE = "/api/v1/work-permits"


async def _one_company_persons(data_factory, *names):
    tenant = await data_factory.ensure_tenant()
    company = await data_factory.create_company(tenant=tenant)
    out = []
    for i, nm in enumerate(names):
        out.append(await data_factory.create_person(tenant=tenant, company=company, first_name=nm, last_name=f"P{i}"))
    return tenant, company, out


@pytest.mark.asyncio
async def test_print_docx_returns_file(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(f"{BASE}", headers=headers,
                                json={"work_type": "height", "zone_text": "фасад", "number": "НД-9"})
    assert r.status_code == 201, r.text
    wp_id = r.json()["id"]

    resp = await async_client.get(f"{BASE}/{wp_id}/print?format=docx", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.content[:2] == b"PK"   # DOCX = zip


@pytest.mark.asyncio
async def test_print_invalid_format_422(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(f"{BASE}", headers=headers,
                                json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    resp = await async_client.get(f"{BASE}/{wp_id}/print?format=xml", headers=headers)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_print_cross_tenant_404(async_client, make_auth_headers):
    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant_slug="ta")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant_slug="tb")
    r = await async_client.post(f"{BASE}", headers=headers_a,
                                json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    resp = await async_client.get(f"{BASE}/{wp_id}/print?format=docx", headers=headers_b)
    assert resp.status_code == 404, resp.text
```

> NB реализатору: сверь фикстуру `make_auth_headers` (поддержка `tenant_slug`) с существующими API-тестами наряда (`tests/api/test_work_permit_signatures_api.py`); если её сигнатура иная — построй cross-tenant сценарий тем же приёмом, что в этих тестах.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_work_permit_print_api.py -p no:cacheprovider 2>&1 | Select-Object -Last 6; echo "EXIT=$LASTEXITCODE"`
Expected: FAIL (404 на /print — эндпоинта нет).

- [ ] **Step 3: Add the endpoint**

В `backend/app/api/routes/work_permits.py` добавить (в конец файла; импорты — к существующим):

```python
from fastapi import Response
from typing import Literal

from app.services.work_permit_print import PdfRendererUnavailable, render_work_permit


@router.get("/{wp_id}/print")
async def print_work_permit_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess,
    format: Literal["docx", "pdf"] = Query("docx"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    try:
        rendered = await render_work_permit(
            session, tenant=tenant, permit_id=wp_id, format_=format,
        ) if False else await render_work_permit(
            session, tenant=tenant, permit_id=wp_id, fmt=format,
        )
    except PdfRendererUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=api_problem_detail(
                code="PDF_RENDERER_UNAVAILABLE",
                message="PDF converter is unavailable",
                error_type="work_permit",
            ),
        ) from exc
    if rendered is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return Response(
        content=rendered.content, media_type=rendered.media_type,
        headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'},
    )
```

> NB реализатору: убери искусственный `if False else` (артефакт примера) — оставь один вызов `await render_work_permit(session, tenant=tenant, permit_id=wp_id, fmt=format)`. `Literal["docx","pdf"]` в `Query` даёт 422 на чужом значении автоматически. `TenantContextValidator` уже импортирован в файле (используется в closing-эндпоинтах) — если нет, добавь импорт по образцу.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_work_permit_print_api.py -p no:cacheprovider 2>&1 | Select-Object -Last 8; echo "EXIT=$LASTEXITCODE"`
Expected: EXIT=0, 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permit_print_api.py
git commit -m "feat(work-permits): эндпоинт GET /{id}/print (docx|pdf) + 503/404/422 (Ф4)"
```

---

### Task 4: Frontend — кнопки скачивания

**Files:**
- Modify: `frontend/src/api/workPermits.ts`
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Test: `frontend/src/pages/work-permits/WorkPermitPrintButtons.test.tsx` (или расширить существующий тест страницы)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/work-permits/WorkPermitPrintButtons.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { PrintButtons } from "@/features/work-permits/PrintButtons";

describe("PrintButtons", () => {
  it("рендерит кнопки скачивания DOCX и PDF", () => {
    render(<PrintButtons onDownload={vi.fn()} />);
    expect(screen.getByRole("button", { name: /DOCX/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PDF/i })).toBeInTheDocument();
  });

  it("клик по DOCX вызывает onDownload('docx')", async () => {
    const onDownload = vi.fn();
    render(<PrintButtons onDownload={onDownload} />);
    screen.getByRole("button", { name: /DOCX/i }).click();
    expect(onDownload).toHaveBeenCalledWith("docx");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/pages/work-permits/WorkPermitPrintButtons.test.tsx`
Expected: FAIL (PrintButtons не найден).

- [ ] **Step 3: Implement**

`frontend/src/features/work-permits/PrintButtons.tsx`:

```tsx
import { Button } from "@/components/ui/button";

interface Props {
  onDownload: (fmt: "docx" | "pdf") => void;
}

export const PrintButtons = ({ onDownload }: Props) => (
  <div className="flex gap-2">
    <Button size="sm" variant="outline" onClick={() => onDownload("docx")}>
      Скачать DOCX
    </Button>
    <Button size="sm" variant="outline" onClick={() => onDownload("pdf")}>
      Скачать PDF
    </Button>
  </div>
);
```

В `frontend/src/api/workPermits.ts` добавить метод скачивания (blob), по образцу существующих файловых выгрузок проекта:

```ts
  async downloadPrint(id: string, fmt: "docx" | "pdf"): Promise<void> {
    const res = await http.get(`/work-permits/${id}/print`, {
      params: { format: fmt }, responseType: "blob",
    });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `work-permit-${id}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  },
```

> NB реализатору: сверь имя http-клиента/обёртки (`http`, `apiClient`, `axios`-instance) и паттерн blob-скачивания с существующими download-кнопками (напр. документы). Если в проекте есть готовый download-хелпер — используй его.

В `WorkPermitDetailPage.tsx` смонтировать `<PrintButtons>` (например, рядом с заголовком/действиями), вызывая `workPermitsApi.downloadPrint(wp.id, fmt)` с `try/catch` → при 503 `toast.error("PDF-конвертер недоступен, скачайте DOCX")`. Гейт — под просмотром (`work_permit.view` — у admin есть; кнопки показывать всем, у кого доступ к странице).

- [ ] **Step 4: Run test + build**

Run: `npm --prefix frontend run test -- src/pages/work-permits/WorkPermitPrintButtons.test.tsx` → passed
Run: `npm --prefix frontend run build` → без ошибок типов/линта (убери неиспользуемые импорты).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/work-permits/PrintButtons.tsx frontend/src/pages/work-permits/WorkPermitPrintButtons.test.tsx frontend/src/api/workPermits.ts frontend/src/pages/work-permits/WorkPermitDetailPage.tsx
git commit -m "feat(work-permits): кнопки скачивания печатного наряда DOCX/PDF (Ф4)"
```

---

### Task 5: Регрессия + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Прогнать когорт наряда-допуска (backend)**

Run (foreground, дождись EXIT): `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_form.py tests/test_work_permit_print_service.py tests/api/test_work_permit_print_api.py tests/test_work_permit_closing_service.py tests/api/test_work_permit_closing_api.py tests/test_work_permit_service.py tests/test_work_permit_signing.py -p no:cacheprovider 2>&1 | Select-Object -Last 8; echo "EXIT=$LASTEXITCODE"`
Expected: EXIT=0.

- [ ] **Step 2: Фронт-регрессия**

Run: `npm --prefix frontend run test -- src/features/work-permits src/pages/work-permits` → passed; `npm --prefix frontend run build` → ок.

- [ ] **Step 3: Записать handoff**

Добавить запись в начало `AI_IMPLEMENTATION_REPORT.md` (после `# AI Implementation Report`): что построено (Ф4 печатный бланк), ветка `feat/work-permits-782n-print` (стек на Ф3b), переиспользование движка печати, новый блок подписей с хэшем, отложенное (типографика официального бланка, тираж на др. виды работ), результат тестов (EXIT). Обновить память контура.

- [ ] **Step 4: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(work-permits): handoff Ф4 «печатный бланк 782н» построен"
```

---

## Self-Review (выполнено автором плана)

- **Покрытие спеки:** §4 сборщик → Task 1; §5 секции → Task 1 (build); §6 блок подписей → Task 1 (таблица) + Task 2 (сбор `SignatureLine` из `signature_requests`); §7 сервис → Task 2; §8 API → Task 3; §9 фронт → Task 4; §10 ошибки (503/404/422/best-effort бланк) → Task 2 (`PdfRendererUnavailable`, try/except бланк) + Task 3 (маппинг); §11 тесты → каждая задача; §12 критерии → Tasks 1-4 + Task 5 регрессия. Гэпов нет.
- **Плейсхолдеры:** код полный в каждом шаге; NB-заметки реализатору указывают на сверку реальных сигнатур (Person.middle_name, LetterheadResolver, http-клиент), а не скрывают логику.
- **Согласованность типов:** `WorkPermitPrintData`/`SignatureLine` (Task 1) используются в Task 2 идентично; `RenderedDoc{content,filename,media_type}` (Task 2) читается в Task 3; `render_work_permit(..., fmt=...)` имя параметра единообразно (artefact `format_` в Task 3 явно помечен к удалению).
- **Известный риск:** letterhead `IssuerRef(company_id=None)` может потребовать company наряда — помечено NB; бланк best-effort (по умолчанию можно `with_letterhead=False` в эндпоинте, если интеграция не сойдётся быстро — отдельный мини-шаг).
