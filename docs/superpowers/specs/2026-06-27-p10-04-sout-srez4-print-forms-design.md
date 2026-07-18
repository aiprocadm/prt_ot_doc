# СОУТ P10-04 срез-4а — печатные формы (Карта СОУТ + Сводная ведомость)

**Дата:** 2026-06-27
**Контур:** СОУТ (специальная оценка условий труда), P10-04
**Срез:** 4а (первый под-срез срез-4); roadmap-пункт «печатные формы»
**Ветка:** `feat/sout-srez4-print-forms-p10-04` (от `origin/main` @ `f72871b6`, после merge срезов 1-3 #696/#697/#698)

## Контекст

Срезы 1-3 СОУТ влиты в main: скелет кампаний/РМ/факторов (#696), версионирование класса
условий труда (#697), полу-авто предложения норм СИЗ/медосмотров (#698). Данные СОУТ
(кампания → рабочие места → факторы/гарантии) уже отдаются read-проекцией
`build_report()` → `CampaignReport`, но выгрузить их в человекочитаемый документ нельзя —
только JSON.

Этот срез добавляет две печатные формы СОУТ как **выгружаемые документы** (DOCX/PDF),
зеркаля проверенный 3-слойный паттерн печати из медосмотров 29н и нарядов-допусков.

## Цель

Сделать результаты СОУТ выгружаемыми в виде двух документов:

1. **Карта СОУТ** — документ на одно рабочее место (по структуре Приказа Минтруда 33н,
   приложение 3, прагматично-верно — без pixel-точного воспроизведения нумерации строк).
2. **Сводная ведомость** — таблица результатов на всю кампанию + статистика по классам.

## Дивиденд без миграции

Обе формы строятся из уже готового `build_report()` → `CampaignReport`. **Ни одной новой
таблицы или колонки.** Миграционный риск = 0. Это явный выбор «дивиденд-дружественного»
пункта срез-4 первым.

## Архитектура — 3-слойный паттерн печати (зеркало medical/work_permits)

### Слой 1 — чистый сборщик `backend/app/domains/sout/print_form.py`

python-docx, без I/O, без SQLAlchemy. Тестируется чистыми юнитами (содержимое DOCX).

```python
@dataclass
class SoutCardFactorRow:
    code: str | None          # код фактора по 29н (тип "4.50")
    name: str                 # наименование фактора
    measured_class: str | None  # raw enum value ("harmful_3_1")

@dataclass
class SoutCardGuaranteeRow:
    kind: str                 # raw enum value ("additional_leave")
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
    assessed_class: str | None   # raw enum value
    assessment_date: str | None
    next_assessment_date: str | None
    factors: list[SoutCardFactorRow]
    guarantees: list[SoutCardGuaranteeRow]

def build_sout_card_docx(data: SoutCardPrintData) -> bytes: ...


@dataclass
class SoutSummaryRow:
    workplace_code: str
    position_name: str
    assessed_class: str | None   # raw enum value
    harmful_factor_count: int    # число факторов с классом 3.1+ (вредные/опасные)
    next_assessment_date: str | None

@dataclass
class SoutSummaryPrintData:
    org_header: str
    generated_at: str | None
    campaign_name: str
    expert_org_name: str | None
    report_number: str | None
    report_date: str | None
    rows: list[SoutSummaryRow]
    class_counts: list[tuple[str, int]]  # [(class_label, count)] в каноническом порядке классов

def build_summary_sheet_docx(data: SoutSummaryPrintData) -> bytes: ...
```

Локальные RU-словари в модуле (конвенция репо — словари локальны в чистом сборщике):

```python
SOUT_CLASS_LABELS = {
    "optimal": "1 (оптимальный)",
    "acceptable": "2 (допустимый)",
    "harmful_3_1": "3.1",
    "harmful_3_2": "3.2",
    "harmful_3_3": "3.3",
    "harmful_3_4": "3.4",
    "dangerous": "4 (опасный)",
}
GUARANTEE_KIND_LABELS = {
    "additional_leave": "Дополнительный отпуск",
    "extra_pay": "Повышенная оплата труда",
    "reduced_hours": "Сокращённая рабочая неделя",
    "milk": "Молоко / лечебно-профилактическое питание",
    "early_pension": "Досрочная пенсия",
    "medical_exam": "Обязательный медосмотр",
}
```

Канонический порядок классов для статистики (и заголовков):
`optimal, acceptable, harmful_3_1, harmful_3_2, harmful_3_3, harmful_3_4, dangerous`.

### Слой 2 — сервис-обёртка `backend/app/services/sout_print.py`

`RenderedDoc` и `PdfRendererUnavailable` объявлены **локально** в этом модуле (СОУТ не
зависит от medical/наряд-контура — урок med02/work_permit_print: контуры не импортируют
типы друг у друга).

```python
class PdfRendererUnavailable(Exception): ...

@dataclass
class RenderedDoc:
    content: bytes
    filename: str
    media_type: str

async def render_sout_card(
    session: AsyncSession, *, tenant: Tenant, workplace_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    # 1. Загрузить workplace (tenant-scoped, не удалён) + его факторы + гарантии + кампанию.
    #    None если workplace не найден / удалён.
    # 2. Собрать SoutCardPrintData (org_header из tenant).
    # 3. build_sout_card_docx(data) -> bytes.
    # 4. fmt="pdf" -> _to_pdf(...) ; иначе RenderedDoc(..., ".docx", _DOCX_MEDIA).

async def render_summary_sheet(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    # Аналогично: загрузить campaign + все workplaces (+ счёт факторов).
    # None если кампания не найдена.

async def _to_pdf(docx_bytes: bytes, *, base_name: str) -> RenderedDoc:
    # convert_docx_bytes(source_bytes=..., timeout_s=45, pool=LibreOfficePool(), passport=None)
    # в asyncio.to_thread; raises PdfRendererUnavailable при сбое/таймауте soffice.
```

Медиа-типы:
- `_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"`
- `_PDF_MEDIA = "application/pdf"`

### Слой 3 — эндпоинты в `backend/app/api/routes/sout.py`

Оба гейтятся существующими `_require_sout_enabled` (feature flag "sout") + `Access`
(`abac(required_roles=["admin"])`).

```python
@router.get("/workplaces/{wid}/card/print")
async def print_sout_card(
    wid: str, tenant: TenantDep, session: SessionDep, access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response: ...

@router.get("/{cid}/summary/print")
async def print_summary_sheet(
    cid: str, tenant: TenantDep, session: SessionDep, access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response: ...
```

Обработка (как в medical/work_permits):
- `await _require_sout_enabled(session, tenant)` сперва.
- `PdfRendererUnavailable` → `HTTPException(503, ...)`.
- `rendered is None` → `HTTPException(404, ...)`.
- Успех → `Response(content, media_type, headers={"Content-Disposition":
  f"attachment; filename*=UTF-8''{quote(filename, safe='')}"})`.
- `Literal["docx","pdf"]` даёт 422 на невалидный формат автоматически.

## Содержание форм (прагматично-верно)

### Карта СОУТ (на одно РМ)

- Шапка: наименование организации (tenant), заголовок «Карта специальной оценки условий труда».
- Реквизиты кампании: эксперт-организация, № отчёта, дата отчёта.
- Идентификация РМ: код РМ, наименование должности.
- Таблица факторов: № / код (29н) / наименование фактора / класс (RU-метка).
- Итоговый класс условий труда по РМ (`assessed_class`, RU-метка; «—» если None).
- Гарантии и компенсации: список `kind`→RU-метка (+ detail, если задан).
- Даты: дата оценки, дата следующей оценки.
- Строка подписей: «Председатель комиссии» и «Члены комиссии» с пустыми линиями
  (реквизиты комиссии не в модели данных — пустые линии для ручного заполнения).

### Сводная ведомость (на кампанию)

- Шапка: организация + «Сводная ведомость результатов СОУТ» + реквизиты кампании.
- Таблица: № / код РМ / должность / итоговый класс / число вредных факторов /
  дата следующей оценки.
- Итоговая статистика по классам: число РМ в каждом классе в каноническом порядке
  (только классы с count > 0 либо все 7 — реализатор выбирает читаемость; статистика
  считается чистым подсчётом по `assessed_class`).

«Число вредных факторов» = факторы с `measured_class` ∈ {harmful_3_1..dangerous}
(класс 3.1 и выше). Чистая функция-хелпер в сборщике/сервисе.

## Фронтенд

`frontend/src/api/sout.ts` — два метода (зеркало `workPermits.downloadPrint`, использует
существующий `downloadBlob` из `utils/download.ts`):

```typescript
async downloadCard(workplaceId: string, fmt: "docx" | "pdf", nameHint?: string): Promise<void>
async downloadSummary(campaignId: string, fmt: "docx" | "pdf", nameHint?: string): Promise<void>
```

`frontend/src/pages/sout/SoutPage.tsx`:
- Кнопка «Карта СОУТ» (docx/pdf) на строке каждого РМ в `ReportPanel`.
- Кнопка «Сводная ведомость» (docx/pdf) на уровне кампании в `ReportPanel`.
- Обработка ошибки (try/catch + сообщение пользователю; 503 = «PDF-конвертер недоступен»).

## Тестирование

**Юниты чистого сборщика** (`tests/test_sout_print_form.py`, по образцу
`test_medical_print_form` — без DB, без async):
- Карта: содержит код/должность РМ, строки факторов с RU-метками классов, итоговый класс,
  гарантии с RU-метками, даты; пустые секции (нет факторов / нет гарантий) рендерятся
  корректно; `assessed_class=None` → «—».
- Сводная: строки по всем РМ, корректная статистика по классам, число вредных факторов,
  пустая кампания (0 РМ) рендерится.

**API-контракт** (`tests/test_sout_print_api.py`, monkeypatch как `test_sout_api.py`):
- `card/print` docx → 200, верный media_type + Content-Disposition.
- `summary/print` docx → 200.
- невалидный `format` → 422.
- `PdfRendererUnavailable` → 503.
- workplace/campaign не найден → 404.
- tenant-изоляция (чужой workplace → 404).

**Фронт-vitest:** кнопки зовут `soutApi.downloadCard`/`downloadSummary` с верным
`format`; ошибка показывает сообщение.

**Гейты:** локально Py3.13.7/.venv (summary-строка теряется на Win — судим по EXIT-коду,
[[py313_win_pytest_invocation]]); канон Py3.12 PG CI = финальный гейт.

## Отложено (явно)

- Реквизиты комиссии СОУТ как структурные поля (председатель/члены — нужна таблица/миграция).
- Фирменный бланк/letterhead на формах (наряд применяет best-effort; для СОУТ не подключаем).
- Снапшот/версии печатных документов (персистентная таблица).
- Пакетная выгрузка всех карт кампании одним архивом (ZIP).
- Декларация соответствия (классы 1-2), импорт файла отчёта СОУТ — другие пункты срез-4,
  отдельные под-срезы.

## Анти-грабли

- `RenderedDoc`/`PdfRendererUnavailable` — **локальные** в `sout_print.py`, не импорт из
  medical/work_permit (контуры независимы).
- RU-словари классов/гарантий — **локальные** в чистом сборщике.
- Миграций НЕТ — печать оборачивает уже вычисляемые проекции; если в диффе появилась
  миграция, что-то пошло не так.
- Канонический порядок классов держать единым (одна константа) — статистика и метки
  не должны разъезжаться.
- Число вредных факторов считать по `measured_class` (фактор), не по `assessed_class` (РМ).
