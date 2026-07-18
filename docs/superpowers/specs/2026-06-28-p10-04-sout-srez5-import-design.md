# P10-04 СОУТ срез-5 «Импорт отчёта СОУТ + валидация» — Design

- **Дата:** 2026-06-28
- **Статус:** проект (design / proposal), ожидает ревью пользователя
- **Контур:** P10-04 СОУТ (TZ B.10 / `vNext §10`)
- **Канон roadmap:** [`docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`](../../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md)
- **Предыдущие срезы:** срез-1 (skeleton), срез-2 (версионирование класса), срез-3 (полу-авто предложения норм), срез-4а (печатные формы), срез-4 (декларация соответствия) — **все влиты в `main`**.

> **Решения brainstorming (выбор пользователя):** формат = **оба (Excel/CSV + ФГИС СОУТ XML)**; семантика = **сверка (diff) с существующей кампанией**; применение = **Preview + Apply (два эндпоинта)**.

---

## 1. Цель

Закрыть давний отложенный пункт P10-04: **загрузка файла отчёта СОУТ → парсинг → валидация → diff против существующей кампании → preview → apply**. Импорт устраняет ручной построчный ввод РМ/факторов/классов и даёт аудиту наглядную сверку «файл vs введённое».

**Ключевой принцип — дивиденд без миграции.** Preview — чистое чтение. Apply пишет **только** в существующие таблицы `sout_workplace` / `sout_factor` / `sout_class_history`, переиспользуя проверенную логику создания РМ и `build_class_history_row`. **Ноль новых таблиц/колонок** — доказывается пустым `git diff origin/main...HEAD -- backend/app/migrations/versions/`.

---

## 2. Архитектура — 3 слоя + тонкий фронт (зеркало срез-4/4а)

### Слой 1 — чистый домен `backend/app/domains/sout/import_report.py`
Без БД, без FastAPI; только библиотеки (как `declaration.py` импортирует python-docx). Здесь же openpyxl/csv/xml-парсинг (детерминированно, читает переданные bytes — побочных эффектов БД нет; тяжёлый openpyxl импортируется лениво внутри функции, как в `documents.py`).

**Датаклассы (нормализованный промежуточный формат):**
```python
@dataclass
class ParsedFactor:
    code: str | None
    name: str
    measured_class: str | None   # значение SoutClass или None (нормализовано)
    class_unparsed: str | None    # исходная строка, если не разобралась (для warning)

@dataclass
class ParsedWorkplace:
    workplace_code: str
    position_name: str
    assessed_class: str | None    # значение SoutClass или None
    class_unparsed: str | None    # исходная строка assessed_class, если не разобралась
    factors: list[ParsedFactor]
```

**Прямой парсер класса** `parse_class_label(raw) -> tuple[str | None, str | None]` → `(class_value, unparsed)`:
- пусто/None → `(None, None)` (класс не указан — допустимо);
- распознано → `(значение SoutClass, None)`;
- не распознано → `(None, исходная_строка)` (для отчёта).
Карта распознавания (регистронезависимо, обрезка пробелов) объединяет: цифровые коды (`"1"`,`"2"`,`"3.1"`..`"3.4"`,`"4"`), коды enum (`"optimal"`,`"acceptable"`,`"harmful_3_1"`..,`"dangerous"`), RU-метки (`"оптимальный"`,`"допустимый"`,`"вредный 3.1"`/`"3.1"`,`"опасный"`) и формы вида `"класс 2"`, `"подкласс 3.1"`. Источник истины меток — `SOUT_CLASS_LABELS`/`SOUT_CLASS_ORDER` из `print_form.py` (один контур, не разъезжается).

**Парсеры форматов** (все → `list[ParsedWorkplace]`):
- `parse_csv(content: bytes) -> list[ParsedWorkplace]` — `csv.DictReader` (идиома `_parse_csv_payload`). Колонки РМ: `workplace_code`, `position_name`, `assessed_class`. Факторы: одна строка = один фактор РМ; строки группируются по `workplace_code` (несколько строк с одним кодом → один РМ с несколькими факторами). Колонки фактора: `factor_code`, `factor_name`, `factor_class`. Заголовки распознаются по русским И английским алиасам (карта `COLUMN_ALIASES`).
- `parse_xlsx(content: bytes) -> list[ParsedWorkplace]` — `openpyxl.load_workbook(read_only=True)`, та же колоночная модель и группировка (идиома `_parse_xlsx_payload`).
- `parse_fgis_xml(content: bytes) -> list[ParsedWorkplace]` — **прагматичный субсет** (см. §6). `xml.etree.ElementTree` (stdlib, без внешних зависимостей). Структура-допущение: `<workplaces><workplace code="" position=""><assessed_class>…</assessed_class><factors><factor code="" name="">КЛАСС</factor>…</factors></workplace>…`. Помечен `TODO: сверить с реальной выгрузкой ФГИС СОУТ`.
- `parse_report(content: bytes, filename: str) -> list[ParsedWorkplace]` — диспетчер по расширению (`.csv`→csv, `.xlsx`→xlsx, `.xml`→xml); неизвестное → `UnsupportedImportFormat` (исключение домена).

**Валидация** `validate_parsed(rows) -> dict[int, RowIssues]` (по индексу строки):
- **Блокирующие ошибки:** пустой `workplace_code`; пустой `position_name`; `class_unparsed` не пуст (assessed_class не разобран); **конфликтующий дубль** `workplace_code` (один код встретился с разными классом/должностью в разных строках). Обычный повтор кода (несколько факторов одного РМ) — НЕ ошибка, строки штатно группируются в один РМ.
- **Предупреждения (не блокируют):** assessed_class ∈ {`optimal`,`acceptable`} И есть фактор ∈ `HARMFUL_CLASSES` (анти-грабли согласованности, как в декларации); любой фактор с `class_unparsed` (класс фактора не разобран — фактор сохранится с `measured_class=None`).

**Diff** `diff_campaign(parsed, existing) -> list[DiffRow]` (чистая функция над двумя нормализованными коллекциями; `existing` — список `(workplace_code, assessed_class_value)`):
- ключ = `workplace_code`;
- `new` — код в файле, нет в БД;
- `changed` — код есть, `assessed_class` отличается;
- `unchanged` — код есть, класс совпадает;
- `removed` — код в БД, нет в файле.

### Слой 2 — сервис `backend/app/services/sout_import.py` (оркестрация БД)
- `_load_existing(session, tenant, cid)` → `[(workplace_code, assessed_class_value), …]` + `{workplace_code: SoutWorkplace}` (для apply).
- `preview_import(session, *, tenant, campaign_id, content, filename) -> ImportOutcome | None`:
  загрузить кампанию (None→`None`→404 в роуте), распарсить+валидировать+`diff_campaign`, собрать построчный отчёт (change + errors + warnings + parsed_class + current_class). **Без записи.**
- `apply_import(session, *, tenant, campaign_id, content, filename) -> ImportResult | None`:
  тот же конвейер. **Всё-или-ничего:** если есть ≥1 блокирующая ошибка → `ImportValidationError` (→422, без записей). Иначе:
  - `new` → создать `SoutWorkplace` (+ `SoutFactor` по факторам) + начальная история (`build_class_history_row(old=None, new=class)`);
  - `changed` → обновить `assessed_class` существующего РМ + `build_class_history_row(old, new)`; **факторы при changed в этом срезе не трогаем** (отложено, см. §7);
  - `unchanged` → пропуск;
  - `removed` → **только подсчёт `removed_detected`, без удаления** (деструктив → отложено).
  Возврат: `ImportResult(created, updated, skipped, removed_detected, errors=[])`.

> `apply` намеренно повторяет parse+validate+diff (не доверяет клиентскому preview) — файл загружается заново, идемпотентность по `workplace_code` гарантирует, что повторный apply того же файла = 0 изменений (всё `unchanged`).

### Слой 3 — эндпоинты в `backend/app/api/routes/sout.py`
Multipart `UploadFile`; фича-флаг `_require_sout_enabled`; admin `Access`; `TenantContextValidator`.
- `POST /sout/{cid}/import/preview` → `ImportPreview`. 404 если кампании нет; 415/422 на `UnsupportedImportFormat`.
- `POST /sout/{cid}/import/apply` → `ImportResult`. Гейт `ensure_campaign_open(campaign.status)` (→409, нельзя импортировать в завершённую/декларированную/отменённую). Блокирующие ошибки → 422 с перечнем. 404 если кампании нет.

### Слой 4 — фронт `frontend/src/api/sout.ts` + `frontend/src/pages/sout/SoutPage.tsx`
- `soutApi.previewImport(campaignId, file)` / `soutApi.applyImport(campaignId, file)` — `FormData`, `multipart/form-data`.
- Секция «Импорт отчёта СОУТ» на уровне кампании: выбор файла → кнопка «Проверить» (preview) → таблица строк с цветовой меткой `new`/`changed`/`unchanged`/`removed` + ошибки/предупреждения по строкам + счётчики → кнопка «Применить» (disabled при `can_apply=false`) → toast результата (создано/обновлено; 409 → «кампания закрыта», 422 → «исправьте ошибки в файле»).

---

## 3. Схемы (`backend/app/schemas/sout.py`, аддитивно, `BaseSchema`)
```python
class ImportFactorRow(BaseSchema):
    code: str | None
    name: str
    parsed_class: str | None
    class_unparsed: str | None

class ImportWorkplaceRow(BaseSchema):
    row_index: int
    workplace_code: str
    position_name: str
    parsed_class: str | None
    current_class: str | None
    change: Literal["new", "changed", "unchanged", "removed"]
    factors: list[ImportFactorRow]
    errors: list[str]
    warnings: list[str]

class ImportPreview(BaseSchema):
    campaign_id: str
    rows: list[ImportWorkplaceRow]
    new_count: int
    changed_count: int
    unchanged_count: int
    removed_count: int
    error_count: int
    can_apply: bool          # error_count == 0

class ImportResult(BaseSchema):
    campaign_id: str
    created: int
    updated: int
    skipped: int
    removed_detected: int
    errors: list[str]        # пусто при успехе; заполнено при 422 (диагностика)
```

---

## 4. Правила валидации (реальная ценность среза)
| Правило | Тип | Поведение |
|---|---|---|
| Пустой `workplace_code` | блокирующая | строка в ошибки, `can_apply=false` |
| Пустой `position_name` | блокирующая | то же |
| `assessed_class` не разобран | блокирующая | то же (исходная строка в сообщении) |
| Конфликтующий дубль `workplace_code` (разные класс/должность) | блокирующая | РМ помечается; обычный повтор-для-факторов не ошибка |
| Класс 1-2 + фактор ≥3.1 | предупреждение | не блокирует apply; видно в preview |
| Класс фактора не разобран | предупреждение | фактор сохраняется с `measured_class=None` |

Ключ diff и идемпотентности — `workplace_code` в рамках кампании.

---

## 5. Тестирование
- **Домен (без БД):** `parse_class_label` (цифры/enum/RU/«класс N»/мусор), `parse_csv`/`parse_xlsx`/`parse_fgis_xml` (включая группировку нескольких факторов одного РМ), `validate_parsed` (каждое правило + анти-грабли класс-2-фактор-3.1), `diff_campaign` (new/changed/unchanged/removed), `parse_report` (диспетчер + `UnsupportedImportFormat`).
- **Сервис (с БД):** `preview_import` (None→404-сигнал; корректный diff против посеянных РМ), `apply_import` (создание new+факторы+история; update changed+история; пропуск unchanged; подсчёт removed; **всё-или-ничего 422** при блокирующей ошибке = 0 записей; идемпотентность повторного apply).
- **API (multipart):** preview 200 / apply 200 / 422 (ошибки) / 409 (кампания закрыта) / 404 (нет кампании) / 415|422 (неизвестный формат) + tenant-isolation (чужая кампания → 404).
- **Фронт vitest:** `previewImport`/`applyImport` (FormData + URL), рендер секции (preview-таблица + блокировка «Применить» при ошибках).
- Среда: Win/.venv Py3.13.7 локально (summary-строка теряется в PowerShell → судить по EXIT-коду). Канон Py3.12 PG CI = финальный гейт.

---

## 6. ФГИС СОУТ XML — прагматичный субсет (честная оговорка)
Реального образца выгрузки ФГИС СОУТ в репозитории нет. `parse_fgis_xml` строится по документированной структуре-допущению (РМ → assessed_class → factors) на `xml.etree.ElementTree` (stdlib). Парсер:
- толерантен к отсутствующим узлам (нет класса → `None`, не падение);
- помечен `TODO: сверить с реальной выгрузкой ФГИС СОУТ` в модуле и в handoff;
- изолирован за общим интерфейсом `list[ParsedWorkplace]` — при появлении реального файла меняется только тело парсера, валидация/diff/apply не трогаются.
Путь Excel/CSV — продакшн-надёжный (реальный переиспользуемый парсер).

---

## 7. Явно отложено (срез-6+)
- Персистентная таблица аудита импортов (кто/когда/файл/результат) — нужна миграция.
- Soft-delete РМ из ветки `removed` (деструктив, требует явного подтверждения UX).
- Авто-резолв `position_id` по `position_name` и `hazard_id` по коду/имени фактора (сейчас сохраняем текстом).
- Обновление **факторов** существующего РМ при `change=changed` (сейчас при changed обновляем только класс).
- Импорт гарантий/компенсаций из файла.
- Реальная валидация схемы ФГИС XML по официальному образцу.

---

## 8. Обязательные правила доработки (§E канона)
Additive-only (миграций нет); не ломать существующие СОУТ-роуты; фича-флаг `sout` уже есть; tenant-isolation на всех границах; переиспользование (`build_class_history_row`, openpyxl/csv-идиома, `SOUT_CLASS_*` метки) вместо дублирования; строгая типизация (backend + frontend); OpenAPI обновляется автоматически из схем.

---

## 9. Self-review (выполнено при написании)
- **Покрытие решений:** оба формата (§2 слой-1 парсеры) ✓; diff против кампании (§2 `diff_campaign`) ✓; preview+apply (§2 слой-2/3) ✓.
- **Дивиденд без миграции:** доказуемо (apply пишет в существующие 3 таблицы; шаг верификации — пустой `git diff` по migrations).
- **Согласованность типов:** `ParsedWorkplace`(domain) ↔ `ImportWorkplaceRow`(schema) — соответствие полей; `change` — общий `Literal` из 4 значений в домене и схеме.
- **Анти-грабли:** класс-2-но-фактор-3.1 — предупреждение и в `validate_parsed`, и в тестах; apply «всё-или-ничего» (а не частичная запись); `removed` не удаляет; повторный apply идемпотентен.
- **Однозначность:** группировка факторов по `workplace_code` зафиксирована (несколько строк CSV/XLSX с одним кодом = один РМ); ключ diff зафиксирован.
