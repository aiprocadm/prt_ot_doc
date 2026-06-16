# Дизайн: авто-применение бланка организации при генерации документов

- **Дата:** 2026-06-15
- **Статус:** утверждён (брейнсторм)
- **Срез:** 1 из 3 (см. «Декомпозиция»)

## Проблема

Движок генерации документов настоящий и рабочий: шаблон DOCX из S3 →
`render_docx` (docxtpl+Jinja2) → `inject_passport` → сохранение в S3
(`_generate_document_for_run`, `backend/app/tasks/_core.py:218`). Модули
брендинга (`app/modules/branding`) и шапок/подвалов (`app/modules/headers`)
качественно реализованы, но **не подключены к конвейеру**:

- `_generate_document_for_run` (`_core.py:353`) делает только `render_docx` +
  `inject_passport`. Вызова бланка нет.
- `run_pack` (`backend/app/api/routes/packs.py:786`) явно передаёт
  `header_text=None, footer_text=None` — пакет печатается без бланка.
- `apply_headers_to_docx` вызывается только из отдельной ручной задачи
  `apply_headers_job` (`_core.py:1436`), запускаемой из
  `app/modules/headers/api.py:151` — по одному документу, постфактум, и без
  подачи branding-контекста.
- `BrandingService.build_profile` дёргается лишь из read-only API брендинга —
  в рендер не подаётся.

Итог: нельзя быстро сформировать документ или пакет «на бланке организации».
Мост уже есть (`build_profile` возвращает `header_context` ровно той формы,
что потребляют плейсхолдеры пресета, и резолвит `preferred_header_preset_code`),
но никто его не вызывает в конвейере.

## Цель Среза 1

Любой документ и любой пакет автоматически выходят на нужном бланке, без
лишних действий, с возможностью переопределить. Эмитентом может быть:

- **company** — любое юрлицо группы компаний тенанта (не только субъект документа);
- **adhoc** — разовый внешний эмитент с inline-реквизитами (без записи в справочник).

Подрядчик как эмитент — Срез 2.

## Ключевые факты кодовой базы

- `Company` — `TenantBaseModel`, на тенант их много; у каждой свои реквизиты
  (`inn`/`kpp`/`ogrn`/адреса/директор/банк), `logo_file_id`, `stamp_file_id`,
  `branding_payload`, `preferred_header_preset_code`
  (`backend/app/models/models.py:639`). «Группа компаний» = несколько `Company`
  под тенантом; отдельной модели группы нет и не требуется.
- Документ имеет `company_id` — это **субъект** документа (например, компания
  работника). Эмитент (чей бланк) может быть другим юрлицом группы.
- `BrandingService.build_profile(company, site?)` отдаёт `BrandingProfileRead`
  с `header_context = {organization, company, branch, doc}` и
  `reproducibility.branding_payload_hash`; есть `resolve_watermark` и
  `render_preview` (`backend/app/modules/branding/service.py:78`).
- `apply_headers_to_docx(docx_bytes, preset, context, watermark_override)`
  возвращает изменённые байты DOCX (`backend/app/modules/headers/engine.py:159`).
- `HeaderFooterPreset` — tenant-scoped, хранит XML шапки/подвала + watermark.

## Концепции

### Эмитент (issuer)

`IssuerRef { kind: "company" | "contractor" | "adhoc", id?, inline? }`:

- **company** — `id` = `company_id` юрлица группы (есть в тенанте). Резолвинг
  реквизитов через `Company`.
- **adhoc** — `inline` несёт реквизиты (`legal_name` обязателен; ИНН/КПП/ОГРН,
  адреса, контакты опционально) + опциональный `logo_file_id`. В справочник не
  пишется.
- **contractor** — Срез 2 (интерфейс закладываем, реализацию не делаем).

**Эмитент ≠ субъект.** У документа остаётся `company_id` (субъект); вводится
понятие issuer (чей бланк), по умолчанию `kind=company, id=company_id`,
переопределяемое на любое юрлицо группы либо на adhoc.

### Разделение «вёрстка vs данные»

- **Пресет = вёрстка** (XML шапки/подвала тенанта, `HeaderFooterPreset`).
- **Контекст = данные** (реквизиты эмитента + поля документа).

Для adhoc переопределяются только данные; вёрстка берётся тенантная. Это
позволяет напечатать на бланке внешнюю компанию без заведения её в справочник.

## Архитектура

### `LetterheadResolver` (новый сервис)

Вход: `(issuer: IssuerRef, site_id | None, doc_type, overrides)`.
Выход: `LetterheadDecision { apply: bool, preset, header_context, watermark }`.

Логика:

1. **Контекст реквизитов:**
   - company → `BrandingService.build_profile(company, site)` → `header_context`.
   - adhoc → inline payload → `header_context` через общий сборщик (ниже).
2. **`doc_type`** прокидывается в `header_context['doc']` (номер/дата/наименование).
3. **Резолвинг пресета:** явный `preset_code` из override → пресет эмитента
   (`Company.preferred_header_preset_code`) → цепочка company/site/tenant (как в
   `build_profile`) → если ничего → `apply=False`.
4. **Watermark:** `BrandingService.resolve_watermark` + override.

### Рефактор `BrandingService`

Выделить `build_header_context(payload: BrandingProfilePayload, site?, doc) ->
header_context`. Тогда:

- `build_profile` = «load `Company` → payload → `build_header_context`» (форма
  выхода не меняется — обратная совместимость).
- adhoc = «inline payload → `build_header_context`».

Форма `header_context` идентична для обоих источников, поэтому движок шапок и
пресеты не различают происхождение реквизитов.

### Вшивание в конвейер

**Одиночная генерация** — `_generate_document_for_run` (`_core.py:353`):
порядок строго `render_docx` → (если `decision.apply`) `apply_headers_to_docx`
→ `inject_passport` → `put_object`. Паспорт ставится **последним**, чтобы его
хеш покрывал финальные байты с бланком. Одна версия документа, без отдельного
`_with_headers.docx`.

**Пакет** — `run_pack` (`packs.py:786`): убрать `header_text=None/footer_text=None`
как механизм бланка; прокидывать `issuer` + override бланка в `context`/metadata
прогона, чтобы тот же резолвер в конвейере применил бланк ко всем документам
пакета.

**Воспроизводимость:** `DocumentSnapshot.render_log` дополняется решением по
бланку (`issuer`, `preset_code`, источник пресета, `branding_payload_hash`).
Для adhoc inline-реквизиты сохраняются в снапшот (по аналогии с
`company_snapshot`) — чтобы потом доказать, на каком бланке вышел документ.

### Override и feature-flag

Override-блок в `POST /documents/generate`, `POST /packs/run`,
`POST /packs/generate`:

```
letterhead: {
  issuer?: { kind, company_id?, inline?: { legal_name, inn?, kpp?, ogrn?,
             legal_address?, actual_address?, contacts?, logo_file_id? } },
  preset_code?: string,
  disabled?: boolean
}
```

- Пусто → авто (issuer = company субъекта, пресет по цепочке).
- `disabled: true` → без бланка.
- `kind=adhoc` → обязателен `inline.legal_name`.

Глобальный флаг `letterhead_auto_apply` в settings (в prod выкатывается
выключенным до проверки, в тестах включён). Согласуется с существующей
`BillingService` capability-проверкой (`documents.generate`).

## Краевые случаи и ошибки

- **Нет пресета и логотипа** → `apply=False`, документ без бланка, решение
  логируется. Это не ошибка.
- **`kind=company`, компании нет в тенанте / soft-deleted** → валидация/404.
- **`kind=adhoc`** → членство в тенанте не требуется; валидируем минимум
  `inline.legal_name` и принадлежность `logo_file_id` тенанту (если задан).
- **Неизвестный `preset_code` в override** → 422.
- **Битый XML пресета / сбой применения бланка** → падаем на стадии с понятной
  ошибкой (не отдаём молча голый документ); обойти можно только `disabled: true`.

## Тестирование

- **Unit (резолвер):** цепочка пресета; дефолтный эмитент vs override; другое
  юрлицо группы; adhoc inline; graceful-без-пресета; `disabled`.
- **Integration:**
  - одиночный документ → в XML колонтитулов есть реквизиты эмитента;
  - пакет → все документы с бланком;
  - override на другую компанию группы → её реквизиты в колонтитулах;
  - adhoc-эмитент → inline-реквизиты в колонтитулах, в справочник ничего не пишется;
  - снапшот/паспорт хранит решение по бланку.
- Переиспользуем существующий тестовый harness `apply_headers`.

## Декомпозиция (общий контекст, не входит в этот спек)

1. **Срез 1 (этот спек):** авто-бланк для своей организации (company) + adhoc;
   резолвер; вшивание в конвейер и пакеты; override; флаг.
2. **Срез 2:** бланк подрядчика — профиль бланка для `ContractorRegistry`
   (логотип, реквизиты, пресет) + эмитент `kind=contractor` + резолвинг
   источника бланка по типу документа.
3. **Срез 3:** UI настройки бланка — загрузка логотипа, реквизиты, конструктор
   шапки/подвала (на `HeaderFooterPreset`), живое превью (на `render_preview`) —
   для своей организации и для подрядчиков.

## Вне объёма Среза 1

- Подрядчик как эмитент (Срез 2).
- UI настройки бланка (Срез 3).
- Per-item выбор разного эмитента внутри одного пакета (общий issuer на пакет;
  гранулярность — позже при необходимости).
- Конструктор/редактор XML-пресетов.
