# Авто-применение бланка организации — план реализации (Срез 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Любой документ и пакет автоматически выходят на фирменном бланке эмитента (любое юрлицо группы либо разовый внешний adhoc-эмитент), с возможностью переопределить или отключить.

**Architecture:** Новый тонкий сервис `LetterheadResolver` поверх готового `BrandingService` отдаёт решение `LetterheadDecision { apply, preset, header_context, watermark }`. Это решение применяется одним проходом внутри `_generate_document_for_run` (`render_docx` → `apply_headers_to_docx` → `inject_passport`), поэтому одиночная генерация, пакеты и batch получают бланк бесплатно. Эмитент — `company` (юрлицо тенанта) или `adhoc` (inline-реквизиты без записи в справочник); подрядчик — Срез 2.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Celery / pydantic v2 / python-docx (через `app.modules.headers.engine`).

**Среда тестов:** запускать `python -m pytest ... -v` (если нет 3.12 — системным python, зафиксировать расхождение версии; см. CLAUDE.md). На Windows — через PowerShell с редиректом вывода в файл, чтобы не зависал.

**Спека:** `docs/superpowers/specs/2026-06-15-letterhead-auto-apply-design.md`

---

## Файловая структура

- **Create** `backend/app/modules/branding/letterhead.py` — `LetterheadResolver` + `LetterheadDecision`.
- **Modify** `backend/app/modules/branding/schemas.py` — `IssuerRef`, `LetterheadOverride`.
- **Modify** `backend/app/modules/branding/service.py` — выделить `assemble_header_context`, добавить `build_adhoc_context`.
- **Modify** `backend/app/core/config.py` — флаг `doc_pipeline_letterhead_auto`.
- **Modify** `backend/app/tasks/_core.py` — вшить резолвер в `_generate_document_for_run`.
- **Modify** `backend/app/api/routes/documents.py` — поле `letterhead` в `DocGenerateRequest`, прокидывание в metadata прогона.
- **Modify** `backend/app/api/routes/packs.py` — поле `letterhead` в `PackRunRequest`, прокидывание в context прогонов.
- **Create** `backend/tests/unit/test_letterhead_resolver.py` — unit-тесты резолвера и сборщика контекста.
- **Create** `backend/tests/api/test_letterhead_pipeline.py` — интеграционные тесты генерации/пакета.

---

## Task 1: Feature-flag `doc_pipeline_letterhead_auto`

**Files:**
- Modify: `backend/app/core/config.py:341`
- Test: `backend/tests/unit/test_letterhead_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_letterhead_resolver.py
from app.core.config import Settings


def test_letterhead_flag_defaults_off():
    settings = Settings()
    assert settings.doc_pipeline_letterhead_auto is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py::test_letterhead_flag_defaults_off -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'doc_pipeline_letterhead_auto'`

- [ ] **Step 3: Add the flag**

In `backend/app/core/config.py`, directly after line 341 (`doc_pipeline_enable_watermark`):

```python
    doc_pipeline_letterhead_auto: bool = Field(False, alias="DOC_PIPELINE_LETTERHEAD_AUTO")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py::test_letterhead_flag_defaults_off -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/unit/test_letterhead_resolver.py
git commit -m "feat(letterhead): add doc_pipeline_letterhead_auto feature flag"
```

---

## Task 2: Схемы `IssuerRef` и `LetterheadOverride`

**Files:**
- Modify: `backend/app/modules/branding/schemas.py` (после `BrandingProfilePayload`, ~строка 72)
- Test: `backend/tests/unit/test_letterhead_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/unit/test_letterhead_resolver.py
import pytest
from pydantic import ValidationError

from app.modules.branding.schemas import IssuerRef, LetterheadOverride


def test_issuer_defaults_to_company_kind():
    issuer = IssuerRef(company_id="c-1")
    assert issuer.kind == "company"
    assert issuer.company_id == "c-1"


def test_adhoc_issuer_requires_legal_name():
    with pytest.raises(ValidationError):
        IssuerRef(kind="adhoc", inline={"inn": "7700000000"})


def test_adhoc_issuer_accepts_inline_legal_name():
    issuer = IssuerRef(kind="adhoc", inline={"legal_name": "ООО Ромашка"})
    assert issuer.inline.legal_name == "ООО Ромашка"


def test_letterhead_override_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        LetterheadOverride(unknown=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py -k issuer -v`
Expected: FAIL with `ImportError: cannot import name 'IssuerRef'`

- [ ] **Step 3: Add the schemas**

In `backend/app/modules/branding/schemas.py`, add `Literal` to the typing import line and append after `BrandingProfilePayload`:

```python
from typing import Any, Literal  # update existing import


class IssuerRef(BaseModel):
    """Кто выпускает документ (чей бланк). Срез 1: company | adhoc."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["company", "contractor", "adhoc"] = "company"
    company_id: str | None = None
    inline: BrandingProfilePayload | None = None

    @model_validator(mode="after")
    def _check_kind(self) -> "IssuerRef":
        if self.kind == "company" and not self.company_id:
            raise ValueError("company_id is required for issuer kind=company")
        if self.kind == "adhoc":
            if self.inline is None or not self.inline.legal_name:
                raise ValueError("inline.legal_name is required for issuer kind=adhoc")
        return self


class LetterheadOverride(BaseModel):
    """Переопределение бланка в запросе генерации/пакета."""

    model_config = ConfigDict(extra="forbid")

    issuer: IssuerRef | None = None
    preset_code: str | None = None
    disabled: bool = False
```

Add `model_validator` to the pydantic import at the top of the file:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py -k "issuer or override" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/branding/schemas.py backend/tests/unit/test_letterhead_resolver.py
git commit -m "feat(letterhead): add IssuerRef and LetterheadOverride schemas"
```

---

## Task 3: Выделить `assemble_header_context` + adhoc-контекст в `BrandingService`

Цель: один сборщик «`BrandingProfilePayload` → `header_context`» для обоих источников (company и adhoc), без изменения формата выхода `build_profile`.

**Files:**
- Modify: `backend/app/modules/branding/service.py` (метод `build_profile`, строки 78–180)
- Test: `backend/tests/unit/test_letterhead_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/unit/test_letterhead_resolver.py
from app.modules.branding.schemas import BrandingProfilePayload


def test_assemble_header_context_shape():
    from app.modules.branding.service import assemble_header_context

    branding = BrandingProfilePayload(legal_name="ООО Тест", inn="7700000000")
    ctx = assemble_header_context(
        branding=branding,
        company_ref={"id": "c-1", "name": "ООО Тест"},
        site=None,
        doc={"title": "Приказ", "number": "12"},
    )
    assert ctx["organization"]["legal_name"] == "ООО Тест"
    assert ctx["company"] == {"id": "c-1", "name": "ООО Тест"}
    assert ctx["branch"] == {}
    assert ctx["doc"] == {"title": "Приказ", "number": "12"}


def test_build_adhoc_context_uses_inline_payload():
    from app.modules.branding.service import build_adhoc_context

    branding = BrandingProfilePayload(legal_name="ООО Внешняя", inn="5500000000")
    ctx = build_adhoc_context(branding=branding, doc={"title": "Договор"})
    assert ctx["organization"]["legal_name"] == "ООО Внешняя"
    # adhoc: компания не из справочника — id отсутствует
    assert ctx["company"]["id"] is None
    assert ctx["company"]["name"] == "ООО Внешняя"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py -k "header_context or adhoc_context" -v`
Expected: FAIL with `ImportError: cannot import name 'assemble_header_context'`

- [ ] **Step 3: Add module-level helpers and refactor `build_profile`**

In `backend/app/modules/branding/service.py`, add two module-level functions (after imports, before `class BrandingService`):

```python
def assemble_header_context(
    *,
    branding: BrandingProfilePayload,
    company_ref: dict[str, Any],
    site: Site | None,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    branch_name = branding.branch_label or (site.name if site is not None else None)
    return {
        "organization": branding.model_dump(),
        "company": company_ref,
        "branch": {"id": site.id, "name": branch_name, "address": site.address} if site else {},
        "doc": doc or {},
    }


def build_adhoc_context(
    *,
    branding: BrandingProfilePayload,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return assemble_header_context(
        branding=branding,
        company_ref={"id": None, "name": branding.legal_name or branding.short_name},
        site=None,
        doc=doc,
    )
```

Then, inside `build_profile`, replace the inline `header_context = {...}` block (currently lines 128–134) with a call to the helper:

```python
        header_context = assemble_header_context(
            branding=branding,
            company_ref={"id": company.id, "name": company.name},
            site=site,
            doc={},
        )
```

- [ ] **Step 4: Run tests to verify pass (incl. no regression in branding API)**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py -k "header_context or adhoc_context" backend/tests/api/test_branding_api.py -v`
Expected: PASS (2 new tests + existing branding API tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/branding/service.py backend/tests/unit/test_letterhead_resolver.py
git commit -m "refactor(branding): extract assemble_header_context, add adhoc context builder"
```

---

## Task 4: `LetterheadResolver`

**Files:**
- Create: `backend/app/modules/branding/letterhead.py`
- Test: `backend/tests/unit/test_letterhead_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/unit/test_letterhead_resolver.py
import pytest

from app.modules.branding.letterhead import LetterheadResolver, LetterheadDecision
from app.modules.branding.schemas import IssuerRef, LetterheadOverride


class _FakeProfile:
    def __init__(self):
        self.preferred_header_preset_code = "default-letterhead"
        self.header_context = {"organization": {"legal_name": "ООО Группа"}, "company": {"id": "c-1", "name": "ООО Группа"}, "branch": {}, "doc": {}}
        self.branding = type("B", (), {"watermark_enabled": False, "watermark_text": None})()
        self.reproducibility = {"branding_payload_hash": "hash-1"}


class _FakeBranding:
    """Минимальный дубль BrandingService для unit-теста резолвера."""

    def __init__(self):
        self.tenant = type("T", (), {"id": "t-1"})()

    async def get_company(self, company_id):
        return type("C", (), {"id": company_id, "name": "ООО Группа", "preferred_header_preset_code": "default-letterhead"})()

    async def get_site(self, site_id):
        return None

    def build_profile(self, *, company, site=None):
        return _FakeProfile()

    async def get_layout_preset(self, preset_code):
        if preset_code is None:
            return None
        return type("P", (), {"code": preset_code, "watermark": {}})()

    def resolve_watermark(self, *, profile, preset, override=None):
        return {"enabled": False}


@pytest.mark.asyncio
async def test_disabled_override_returns_no_apply():
    resolver = LetterheadResolver(_FakeBranding())
    decision = await resolver.resolve(
        issuer=IssuerRef(company_id="c-1"),
        site_id=None,
        doc={},
        override=LetterheadOverride(disabled=True),
    )
    assert decision.apply is False


@pytest.mark.asyncio
async def test_company_issuer_resolves_preset_from_chain():
    resolver = LetterheadResolver(_FakeBranding())
    decision = await resolver.resolve(issuer=IssuerRef(company_id="c-1"), site_id=None, doc={}, override=None)
    assert decision.apply is True
    assert decision.preset_code == "default-letterhead"
    assert decision.header_context["company"]["id"] == "c-1"
    assert decision.branding_payload_hash == "hash-1"


@pytest.mark.asyncio
async def test_contractor_issuer_not_supported_in_slice_1():
    resolver = LetterheadResolver(_FakeBranding())
    with pytest.raises(NotImplementedError):
        await resolver.resolve(issuer=IssuerRef(kind="contractor", company_id="x"), site_id=None, doc={}, override=None)


@pytest.mark.asyncio
async def test_explicit_unknown_preset_raises():
    """Явно заданный, но несуществующий preset_code — ошибка (≠ мягкий 'нет пресета')."""
    class _NoPresetBranding(_FakeBranding):
        async def get_layout_preset(self, preset_code):
            return None

    resolver = LetterheadResolver(_NoPresetBranding())
    with pytest.raises(ValueError):
        await resolver.resolve(
            issuer=IssuerRef(company_id="c-1"),
            site_id=None,
            doc={},
            override=LetterheadOverride(preset_code="does-not-exist"),
        )


@pytest.mark.asyncio
async def test_adhoc_issuer_builds_inline_context():
    resolver = LetterheadResolver(_FakeBranding())
    issuer = IssuerRef(kind="adhoc", inline={"legal_name": "ООО Внешняя"})
    decision = await resolver.resolve(issuer=issuer, site_id=None, doc={}, override=LetterheadOverride(preset_code="default-letterhead"))
    assert decision.apply is True
    assert decision.header_context["organization"]["legal_name"] == "ООО Внешняя"
    assert decision.header_context["company"]["id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py -k "disabled or company_issuer or contractor or adhoc_issuer" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.branding.letterhead'`

- [ ] **Step 3: Implement the resolver**

```python
# backend/app/modules/branding/letterhead.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.branding.schemas import BrandingProfilePayload, IssuerRef, LetterheadOverride
from app.modules.branding.service import BrandingService, build_adhoc_context


@dataclass
class LetterheadDecision:
    apply: bool
    preset: Any = None
    header_context: dict[str, Any] = field(default_factory=dict)
    watermark: dict[str, Any] = field(default_factory=dict)
    issuer_kind: str = "company"
    issuer_id: str | None = None
    preset_code: str | None = None
    branding_payload_hash: str | None = None

    def as_render_log(self) -> dict[str, Any]:
        return {
            "applied": self.apply,
            "issuer_kind": self.issuer_kind,
            "issuer_id": self.issuer_id,
            "preset_code": self.preset_code,
            "branding_payload_hash": self.branding_payload_hash,
        }


class LetterheadResolver:
    """Решает, какой бланк и контекст применить при генерации документа."""

    def __init__(self, branding: BrandingService) -> None:
        self._branding = branding

    async def resolve(
        self,
        *,
        issuer: IssuerRef,
        site_id: str | None,
        doc: dict[str, Any] | None,
        override: LetterheadOverride | None,
    ) -> LetterheadDecision:
        if override is not None and override.disabled:
            return LetterheadDecision(apply=False, issuer_kind=issuer.kind, issuer_id=issuer.company_id)

        preset_code_override = override.preset_code if override is not None else None

        if issuer.kind == "contractor":
            raise NotImplementedError("contractor issuer is delivered in Slice 2")

        if issuer.kind == "adhoc":
            branding = issuer.inline or BrandingProfilePayload()
            header_context = build_adhoc_context(branding=branding, doc=doc)
            preset = await self._branding.get_layout_preset(preset_code_override)
            if preset is None:
                if preset_code_override:
                    raise ValueError(f"letterhead preset not found: {preset_code_override}")
                return LetterheadDecision(apply=False, issuer_kind="adhoc", issuer_id=None)
            watermark = self._resolve_watermark_for_payload(branding, preset, override)
            return LetterheadDecision(
                apply=True,
                preset=preset,
                header_context=header_context,
                watermark=watermark,
                issuer_kind="adhoc",
                issuer_id=None,
                preset_code=preset.code,
                branding_payload_hash=None,
            )

        # kind == "company"
        company = await self._branding.get_company(issuer.company_id)
        site = await self._branding.get_site(site_id)
        profile = self._branding.build_profile(company=company, site=site)
        if doc:
            profile.header_context = {**profile.header_context, "doc": doc}
        effective_code = preset_code_override or profile.preferred_header_preset_code
        preset = await self._branding.get_layout_preset(effective_code)
        if preset is None:
            if preset_code_override:
                raise ValueError(f"letterhead preset not found: {preset_code_override}")
            return LetterheadDecision(apply=False, issuer_kind="company", issuer_id=company.id)
        watermark = self._branding.resolve_watermark(
            profile=profile,
            preset=preset,
            override=(override.model_dump().get("watermark") if override is not None else None),
        )
        return LetterheadDecision(
            apply=True,
            preset=preset,
            header_context=profile.header_context,
            watermark=watermark,
            issuer_kind="company",
            issuer_id=company.id,
            preset_code=preset.code,
            branding_payload_hash=profile.reproducibility.get("branding_payload_hash"),
        )

    def _resolve_watermark_for_payload(self, branding: BrandingProfilePayload, preset: Any, override: LetterheadOverride | None) -> dict[str, Any]:
        watermark = {"enabled": bool(branding.watermark_enabled), "text": branding.watermark_text}
        if not watermark.get("text"):
            watermark["enabled"] = False
        return watermark
```

> Примечание: `LetterheadOverride` не имеет поля `watermark`; `override.model_dump().get("watermark")` вернёт `None`, что корректно. Поле watermark-override в API можно добавить позже без изменения резолвера.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/test_letterhead_resolver.py -v`
Expected: PASS (все тесты файла)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/branding/letterhead.py backend/tests/unit/test_letterhead_resolver.py
git commit -m "feat(letterhead): add LetterheadResolver with company and adhoc issuers"
```

---

## Task 5: Вшить резолвер в конвейер генерации

**Files:**
- Modify: `backend/app/tasks/_core.py` (импорты ~строка 82; тело `_generate_document_for_run` строки 311–417)
- Test: `backend/tests/api/test_letterhead_pipeline.py`

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/api/test_letterhead_pipeline.py
import pytest

pytestmark = pytest.mark.asyncio


async def test_generated_document_carries_issuer_letterhead(letterhead_fixture):
    """
    fixture готовит: тенант с пресетом 'default-letterhead', компанию-эмитента с
    реквизитами и preferred_header_preset_code, простой DOCX-шаблон с sectPr,
    флаг doc_pipeline_letterhead_auto=True. Возвращает helper для запуска
    _generate_document_for_run и чтения сохранённого DOCX из storage.
    """
    document_bytes = await letterhead_fixture.generate_and_fetch(
        company_id=letterhead_fixture.issuer_company_id,
        letterhead=None,  # авто
    )
    headers_xml = letterhead_fixture.read_header_xml(document_bytes)
    assert "ООО Группа" in headers_xml  # legal_name эмитента попал в колонтитул


async def test_disabled_letterhead_produces_no_headers(letterhead_fixture):
    document_bytes = await letterhead_fixture.generate_and_fetch(
        company_id=letterhead_fixture.issuer_company_id,
        letterhead={"disabled": True},
    )
    assert letterhead_fixture.read_header_xml(document_bytes) == ""
```

> Реализуй фикстуру `letterhead_fixture` в `backend/tests/api/conftest.py` (или локально в файле), переиспользуя существующие фабрики тенанта/компании из `tests/api/test_branding_api.py` и helper создания `HeaderFooterPreset`. Шаблон DOCX можно собрать минимальным python-docx документом (он содержит `sectPr` по умолчанию).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py -v`
Expected: FAIL (бланк не применяется — `headers_xml` пуст / не содержит реквизитов)

- [ ] **Step 3: Wire the resolver into `_generate_document_for_run`**

Add imports near `backend/app/tasks/_core.py:82`:

```python
from app.modules.branding.letterhead import LetterheadResolver
from app.modules.branding.schemas import IssuerRef, LetterheadOverride
from app.modules.branding.service import BrandingService
```

Inside `_generate_document_for_run`, replace the render block (currently lines 352–354):

```python
                try:
                    rendered_base = render_docx(template_bytes, context_payload)
                    rendered = inject_passport(rendered_base, passport, visible=True)
```

with letterhead-aware rendering:

```python
                try:
                    rendered_base = render_docx(template_bytes, context_payload)
                    letterhead_decision = None
                    if settings.doc_pipeline_letterhead_auto:
                        tenant = await session.get(Tenant, run.tenant_id)
                        raw_letterhead = metadata.get("letterhead")
                        override = LetterheadOverride.model_validate(raw_letterhead) if raw_letterhead else None
                        issuer = (
                            override.issuer
                            if override is not None and override.issuer is not None
                            else IssuerRef(kind="company", company_id=company.id)
                        )
                        resolver = LetterheadResolver(BrandingService(session, tenant))
                        letterhead_decision = await resolver.resolve(
                            issuer=issuer,
                            site_id=metadata.get("site_id"),
                            doc={"title": template.name, "generated_at": now.isoformat()},
                            override=override,
                        )
                    if letterhead_decision is not None and letterhead_decision.apply:
                        rendered_base, _report = apply_headers_to_docx(
                            docx_bytes=rendered_base,
                            preset=letterhead_decision.preset,
                            context=letterhead_decision.header_context,
                            watermark_override=letterhead_decision.watermark,
                        )
                    rendered = inject_passport(rendered_base, passport, visible=True)
```

In the `DocumentSnapshot(...)` construction (the `render_log={...}` block, ~lines 410–414), add the letterhead decision:

```python
                    render_log={
                        "pipeline_run_id": run.id,
                        "status": "generated",
                        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                        "letterhead": letterhead_decision.as_render_log() if letterhead_decision else {"applied": False},
                    },
```

> `apply_headers_to_docx` уже импортирован (`_core.py:82`). `Tenant` уже импортирован (`_core.py:66`). `render_docx` импортируется в этом модуле — оставить как есть.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py -v`
Expected: PASS (2 теста)

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/_core.py backend/tests/api/test_letterhead_pipeline.py backend/tests/api/conftest.py
git commit -m "feat(letterhead): apply issuer letterhead inside document generation pipeline"
```

---

## Task 6: Прокинуть `letterhead` через `POST /documents/generate`

**Files:**
- Modify: `backend/app/api/routes/documents.py` (`DocGenerateRequest` строки 241–257; сборка metadata прогона в `generate_document`)
- Test: `backend/tests/api/test_letterhead_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/api/test_letterhead_pipeline.py
async def test_generate_endpoint_accepts_letterhead_override(api_client, letterhead_fixture):
    resp = await api_client.post(
        "/api/v1/documents/generate",
        json={
            "template_code": letterhead_fixture.template_code,
            "template_version": 1,
            "company_id": letterhead_fixture.subject_company_id,
            "letterhead": {"issuer": {"kind": "company", "company_id": letterhead_fixture.issuer_company_id}},
        },
        headers=letterhead_fixture.auth_headers,
    )
    assert resp.status_code == 202
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py::test_generate_endpoint_accepts_letterhead_override -v`
Expected: FAIL — `extra="forbid"` отклоняет неизвестное поле `letterhead` (422)

- [ ] **Step 3: Add the field and thread into metadata**

In `backend/app/api/routes/documents.py`, import the schema near the top:

```python
from app.modules.branding.schemas import LetterheadOverride
```

Add to `DocGenerateRequest` (after `npa_binding_id`, line 257):

```python
    letterhead: LetterheadOverride | None = Field(default=None)
```

In `generate_document`, where the pipeline-run metadata dict is assembled (the dict that already carries `company_id`, `person_id`, `initiated_by`, `correlation_id`), add the letterhead payload:

```python
        metadata["letterhead"] = payload.letterhead.model_dump(mode="json") if payload.letterhead else None
        metadata["site_id"] = getattr(payload, "site_id", None)
```

> Если в `DocGenerateRequest` нет `site_id`, использовать `None` (Срез 1 берёт site из metadata только когда задан). Точка сборки metadata — внутри `generate_document` (documents.py:1237+), рядом с уже существующими ключами прогона.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py::test_generate_endpoint_accepts_letterhead_override -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/documents.py backend/tests/api/test_letterhead_pipeline.py
git commit -m "feat(letterhead): accept letterhead override in /documents/generate"
```

---

## Task 7: Прокинуть `letterhead` через `POST /packs/run`

**Files:**
- Modify: `backend/app/api/routes/packs.py` (`PackRunRequest`; `_build_context` / metadata прогонов в `run_pack` строки 737–791)
- Test: `backend/tests/api/test_letterhead_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/api/test_letterhead_pipeline.py
async def test_pack_run_applies_letterhead_to_all_documents(api_client, letterhead_fixture):
    resp = await api_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": letterhead_fixture.pack_code,
            "company_id": letterhead_fixture.subject_company_id,
            "person_ids": [letterhead_fixture.person_id],
            "letterhead": {"issuer": {"kind": "company", "company_id": letterhead_fixture.issuer_company_id}},
        },
        headers=letterhead_fixture.auth_headers,
    )
    assert resp.status_code == 202
    # после прогона каждый сгенерированный документ должен нести бланк эмитента
    for document_bytes in letterhead_fixture.fetch_pack_documents(resp.json()["batch_id"]):
        assert "ООО Группа" in letterhead_fixture.read_header_xml(document_bytes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py::test_pack_run_applies_letterhead_to_all_documents -v`
Expected: FAIL — поле `letterhead` не принимается / бланк не применяется

- [ ] **Step 3: Add field and thread into run metadata**

In `backend/app/api/routes/packs.py`, import the schema and add the field to `PackRunRequest`:

```python
from app.modules.branding.schemas import LetterheadOverride
```

```python
    letterhead: LetterheadOverride | None = None
```

In `run_pack`, when each run is created via `service.ensure_pending_run(...)` (lines 780–791), the resolver in the pipeline reads `metadata["letterhead"]`/`metadata["site_id"]`. Ensure those keys are populated on the run metadata. `ensure_pending_run` builds the run from `context`; add the letterhead payload and site to the per-run metadata. Locate where the run's `result_metadata` is initialised inside `PipelineService.ensure_pending_run` and pass through, OR set it on the context consumed by the pipeline:

```python
                context = _build_context(
                    pack=pack,
                    company=company,
                    site=site,
                    person=person,
                    payload=payload,
                )
                context["letterhead"] = payload.letterhead.model_dump(mode="json") if payload.letterhead else None
                context["site_id"] = site.id if site else None
```

Then in `_generate_document_for_run` (Task 5) read from `metadata` first and fall back to `run.context` for pack-originated runs:

```python
                        raw_letterhead = metadata.get("letterhead") or (run.context or {}).get("letterhead")
                        ...
                        site_id=metadata.get("site_id") or (run.context or {}).get("site_id"),
```

Apply that two-source read in the Task 5 block.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py::test_pack_run_applies_letterhead_to_all_documents -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/packs.py backend/app/tasks/_core.py backend/tests/api/test_letterhead_pipeline.py
git commit -m "feat(letterhead): apply letterhead across pack-generated documents"
```

---

## Task 8: Интеграционные тесты — группа компаний и adhoc-эмитент

**Files:**
- Test: `backend/tests/api/test_letterhead_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/api/test_letterhead_pipeline.py
async def test_override_to_other_group_company_uses_its_requisites(api_client, letterhead_fixture):
    """Субъект документа — дочерняя компания, эмитент — управляющая компания группы."""
    document_bytes = await letterhead_fixture.generate_and_fetch(
        company_id=letterhead_fixture.subject_company_id,
        letterhead={"issuer": {"kind": "company", "company_id": letterhead_fixture.managing_company_id}},
    )
    headers_xml = letterhead_fixture.read_header_xml(document_bytes)
    assert "ООО Управляющая" in headers_xml
    assert "ООО Дочерняя" not in headers_xml


async def test_adhoc_issuer_prints_inline_requisites_without_persisting(api_client, letterhead_fixture):
    document_bytes = await letterhead_fixture.generate_and_fetch(
        company_id=letterhead_fixture.subject_company_id,
        letterhead={
            "issuer": {"kind": "adhoc", "inline": {"legal_name": "ООО Разовая", "inn": "9900000000"}},
            "preset_code": letterhead_fixture.preset_code,
        },
    )
    headers_xml = letterhead_fixture.read_header_xml(document_bytes)
    assert "ООО Разовая" in headers_xml
    # adhoc не пишется в справочник компаний
    assert letterhead_fixture.company_count_unchanged()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py -k "group_company or adhoc_issuer_prints" -v`
Expected: FAIL until the fixture exposes `managing_company_id` and `company_count_unchanged()`; resolver logic from Task 4 already supports both paths.

- [ ] **Step 3: Extend the fixture**

Add to `letterhead_fixture`: a `managing_company_id` (a second `Company` in the same tenant with `legal_name="ООО Управляющая"`), a `subject_company_id` (`"ООО Дочерняя"`), and `company_count_unchanged()` (snapshot count of `Company` rows before/after generation, assert equal).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/api/test_letterhead_pipeline.py -v`
Expected: PASS (весь файл)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/api/test_letterhead_pipeline.py backend/tests/api/conftest.py
git commit -m "test(letterhead): cover group-company override and adhoc issuer"
```

---

## Финальная проверка

- [ ] Прогнать обе группы тестов:
  `python -m pytest backend/tests/unit/test_letterhead_resolver.py backend/tests/api/test_letterhead_pipeline.py backend/tests/api/test_branding_api.py -v`
- [ ] Включить флаг в dev-конфиге (`DOC_PIPELINE_LETTERHEAD_AUTO=true`) и сгенерировать один документ + один пакет вручную, убедиться в наличии бланка.
- [ ] Оставить флаг выключенным в prod-конфиге до отдельного решения о выкатке.

## Definition of Done (Срез 1)

- Документы и пакеты при включённом флаге выходят на бланке эмитента-компании автоматически.
- Эмитент переопределяется на любое юрлицо группы и на adhoc-внешнюю компанию (inline-реквизиты, без записи в справочник).
- `disabled: true` отключает бланк; отсутствие пресета не ломает генерацию.
- Решение по бланку фиксируется в `DocumentSnapshot.render_log`.
- Все новые тесты зелёные; `test_branding_api.py` без регрессий.
