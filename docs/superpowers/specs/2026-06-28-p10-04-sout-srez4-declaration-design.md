# P10-04 СОУТ срез-4 — Декларация соответствия условий труда (design)

**Дата:** 2026-06-28
**Контур:** P10-04 СОУТ (TZ Section B.10), срез-4 (после печатных форм срез-4а)
**Ветка:** `feat/sout-srez4-declaration-p10-04` (от `origin/main` @ `87a21373`)
**Тип:** дивиденд-дружественный под-срез (read-проекция + печать, **без миграции**)

---

## Цель

Реализовать **декларацию соответствия условий труда государственным нормативным
требованиям охраны труда** (ст. 11 ФЗ-426, форма по Приказу Минтруда России от
17.06.2021 № 406н). Работодатель подаёт декларацию в территориальный орган
Роструда для рабочих мест, где условия признаны **оптимальными (класс 1)** или
**допустимыми (класс 2)** и не выявлено вредных/опасных факторов.

Это естественное продолжение СОУТ: lifecycle уже содержит переход
`COMPLETED → DECLARED`. Срез делает результаты СОУТ выгружаемой декларацией
(DOCX/PDF) и даёт read-preview «какие РМ подлежат декларированию, а какие нет».

## Дивиденд без миграции

Критерий отбора вычислим из уже готовых данных (`SoutWorkplace.assessed_class` +
`SoutFactor.measured_class`). Декларация строится из той же read-проекции, что
`build_report` / печатные формы. **`git diff origin/main...HEAD` не должен
содержать ни одного файла под `migrations/versions/`.** Миграционный риск = 0.

## Решения brainstorming (2026-06-28)

1. **Объём:** полный вертикальный срез (домен + сервис + 2 эндпоинта + фронт).
2. **Критерий отбора:** консервативно-юридический — `assessed_class ∈ {optimal,
   acceptable}` **И** `harmful_factor_count(factors) == 0`. Любой вредный фактор
   (класс 3.1+) дисквалифицирует РМ, даже если итоговый класс проставлен 1-2.
   Preview показывает оба списка: eligible + ineligible с причиной.
3. **Реквизиты работодателя (ИНН/ОГРН/адрес):** плейсхолдеры (заполняемые вручную
   прочерки), `org_header = tenant.name`. Печать СОУТ остаётся самодостаточной —
   без миграции и без импорта branding-модуля. Ничего не выдумываем.

## Архитектура — 3 слоя (зеркало среза-4а)

### Слой 1 — чистый домен `domains/sout/declaration.py`

Без `sqlalchemy` / без I/O. Импортирует из соседнего `print_form.py` (внутри
контура, не cross-contour): `harmful_factor_count`, `class_label`,
`HARMFUL_CLASSES`.

```python
DECLARABLE_CLASSES = frozenset({"optimal", "acceptable"})

def evaluate_eligibility(
    assessed_class: str | None, factors: list[SoutCardFactorRow]
) -> tuple[bool, str | None]:
    """Подлежит ли РМ декларированию. Возвращает (eligible, ineligible_reason)."""
    if assessed_class is None:
        return False, "класс условий труда не проставлен"
    if assessed_class not in DECLARABLE_CLASSES:
        return False, f"класс {class_label(assessed_class)} — вредные/опасные условия"
    if harmful_factor_count(factors) > 0:
        return False, "выявлен вредный фактор (класс 3.1+)"
    return True, None
```

Dataclasses:
- `DeclarationRow(workplace_code, position_name, assessed_class, headcount,
  report_ref, eligible, ineligible_reason)`
- `DeclarationPrintData(org_header, generated_at, employer_inn, employer_ogrn,
  employer_address, campaign_name, report_number, report_date, rows)` — где
  employer_* по умолчанию None → печатается прочерк.

`build_declaration_docx(data) -> bytes` (python-docx):
- Заголовок «Декларация соответствия условий труда государственным нормативным
  требованиям охраны труда».
- Блок работодателя: «Наименование работодателя: {org_header}», «ИНН: ____»,
  «ОГРН: ____», «Адрес: ____» (прочерки через общий `_kv`-стиль с «—»/подчёрк).
- Основание: «Отчёт о проведении СОУТ № {report_number} от {report_date}».
- Таблица декларируемых РМ (только eligible): № / Код РМ / Должность /
  Численность работников / Реквизиты отчёта СОУТ. Численность = «1» если у РМ
  есть `person_id`, иначе «—».
- Строка подписи руководителя: «Руководитель: ____________ / ____________».
- Факт-нота (с пометкой `# TODO: сверить с юристом` в коде, как HV-минимумы):
  декларация подаётся в территориальный орган Роструда; действует с учётом
  ст. 11 ФЗ-426.
- Если eligible-строк нет — «Нет рабочих мест, подлежащих декларированию.».

### Слой 2 — сервис `services/sout_declaration.py` (зеркало `sout_print.py`)

- Переиспользует `RenderedDoc`, `PdfRendererUnavailable` и PDF-конвертацию
  (`_to_pdf`) из `app.services.sout_print` — внутри контура, DRY. (Если `_to_pdf`
  останется приватным, при реализации вынести общий helper или продублировать
  ~12 строк; решает план — приоритет: не плодить cross-contour связь.)
- `build_declaration_projection(*, campaign, workplaces_with_factors)
  -> list[DeclarationRow]` — чистая сборка (тестируется без БД); каждая строка
  получает eligible/reason из `evaluate_eligibility`.
- `render_declaration(session, *, tenant, campaign_id, fmt="docx")
  -> RenderedDoc | None` — tenant-scoped загрузка кампании (None → None →
  роут 404), загрузка РМ + факторов (паттерн `_load_factors` из sout_print),
  проекция, **в DOCX идут только eligible-строки**, опц. PDF через `_to_pdf`.
- `base_name = "sout-declaration"`.

### Слой 3 — эндпоинты в `api/routes/sout.py`

- `GET /sout/{cid}/declaration` → `DeclarationPreview`:
  read-проекция (eligible + ineligible с причинами + счётчики).
  `_require_sout_enabled` + `Access` (admin) + `TenantContextValidator`.
  Загружает кампанию (404 если нет), РМ + факторы, строит проекцию через домен.
- `GET /sout/{cid}/declaration/print?format=docx|pdf` → `Response`
  (`_doc_response`). `PdfRendererUnavailable` → 503 (`_pdf_unavailable`),
  None → 404. Полностью повторяет `print_summary_sheet`.

## Схемы `schemas/sout.py`

```python
class DeclarationRowRead(BaseModel):
    workplace_code: str
    position_name: str
    assessed_class: str | None
    headcount: str            # "1" | "—"
    report_ref: str | None
    eligible: bool
    ineligible_reason: str | None

class DeclarationPreview(BaseModel):
    campaign_id: str
    campaign_name: str
    eligible: list[DeclarationRowRead]
    ineligible: list[DeclarationRowRead]
    eligible_count: int
    ineligible_count: int
```

## Фронт

- `frontend/src/api/sout.ts`: `getDeclaration(cid)` (JSON), `downloadDeclaration(cid,
  fmt)` (responseType blob + общий `downloadBlob`).
- В `ReportPanel`/`SoutPage` — секция «Декларация соответствия»: счётчики
  eligible/ineligible, списки РМ (ineligible с причиной), кнопки «Декларация
  DOCX / PDF». Обработка ошибок: try/catch + sonner toast (503-PDF →
  «PDF-конвертер недоступен, скачайте DOCX»; иначе «Не удалось скачать документ»).

## Поток данных

`SoutCampaign` + `SoutWorkplace` + `SoutFactor` (те же строки, что `build_report`)
→ доменная eligibility-проекция → `DeclarationPreview` (read) **и** DOCX/PDF
(только eligible). Никакой записи в БД — чистый read + рендер.

## Тестирование

**Домен-юниты** (`tests/test_sout_declaration.py`):
- eligibility: класс 1 (optimal) eligible; класс 2 (acceptable) eligible;
  класс 3.1+ ineligible с верной причиной; `None` ineligible; **класс 2 + фактор
  3.1 → ineligible** (ключевой анти-грабли кейс); фактор класса 1-2 не дисквалиф.
- `build_declaration_docx` отдаёт непустые байты (валидный DOCX/ZIP); нумерация
  строк; пустой eligible-список → строка-заглушка.

**Сервис DB-тесты** (`tests/test_sout_declaration_service.py`):
- проекция собирается из РМ+факторов; None-кампания → None; tenant-изоляция;
  в DOCX попадают только eligible.

**API** (`tests/test_sout_declaration_api.py`):
- preview 200 (shape eligible/ineligible/counts); print docx 200; invalid format
  → 422; feature-off → 404; tenant-изоляция (чужая кампания → 404).

**Фронт vitest**:
- рендер секции (eligible/ineligible счётчики и списки); вызовы getDeclaration /
  downloadDeclaration; error-path (503 → toast).

Среда: Win + Py3.13.7/.venv (summary-строка теряется на Win — судим по EXIT-коду,
см. py313-win-pytest-invocation). Канон Py3.12.12 PG CI = финальный гейт.

## Явно отложено (вне среза)

- Персистентная запись поданной декларации + №/дата подачи + переход кампании в
  статус `DECLARED` (нужна таблица/миграция → отдельный срез-4в).
- Реальная агрегатная численность работников на РМ (сейчас 1/«—» по `person_id`).
- Реквизиты заключения эксперта как структурные поля.
- ZIP-пакет декларации + карт РМ.
- Реквизиты работодателя из Company/branding (сейчас плейсхолдеры).

## Анти-грабли

- Импорт `harmful_factor_count`/`class_label` из `print_form.py` — внутри контура
  СОУТ (не cross-contour); RU-метки остаются локальными в чистом слое.
- `harmful_factor_count` считает по `measured_class` фактора (3.1+), не по
  итоговому классу РМ — так класс-2-но-с-фактором-3.1 честно дисквалифицируется.
- `RenderedDoc`/`PdfRendererUnavailable` берём из `sout_print` (один контур), не
  из medical/work_permits.
- `_raw()` коэрсит enum→`.value` (как в sout_print) — печать работает и с enum, и
  с raw-строкой.
- Печать в DOCX — только eligible-строки; ineligible видны лишь в read-preview
  (нельзя задекларировать вредное РМ).
