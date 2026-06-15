# ЭДО Срез-3: код-flow для briefing — дизайн

**Дата:** 2026-06-13
**Контур:** ЭДО / подпись (ТЗ раздел B.5, vNext §6.9 «ПЭП для внутреннего контура», §6.10 «история ознакомлений»)
**Ветка:** `feat/edo-briefing-code-flow`
**Статус до среза:** ПЭП-ядро влито (Срез-1 PR #649 → `974cd30`, Срез-2-мини PR #650 → `a006d6e`). Подпись ознакомления с инструктажем (`BriefingEntryService.sign`) идёт **только как attested-подпись** — `PepSigningService.create_attested` ставит `signed` мгновенно, без разового кода. Сотрудник без учётки фактически код не вводит — фиксация подписи отражает присутствие оформителя, а не подтверждение работником. Был обозначен «Не-целью» Среза-1 (`2026-06-11-edo-pep-signing-design.md:22`).
**Статус после среза:** ✅ РЕАЛИЗОВАНО И ВЛИТО — PR #652 (`cd57127`) + PR #653 (`ad900c4`). Двухфазный код-flow: `POST /briefings/entries/{id}/sign-employee` (выдаёт 6-значный код) → `POST /briefings/entries/{id}/confirm-code` (создаёт `BriefingSignature`); флаг `BriefingTemplate.require_signature_code`, миграция `ed04`, attested-путь сохранён как fallback (back-compat), сервис/API/тесты + demo-seed. Проверено аудитом кода 2026-06-15.

## 1. Цель среза

Сделать подпись ознакомления с инструктажем **опционально** проходящей через настоящий код-flow ПЭП: работник без учётки подтверждает ознакомление **разовым 6-значным кодом** (как уже сделано для документов). Включение — политикой на шаблоне инструктажа (`require_signature_code`), чтобы тенант сам решал, для каких типов инструктажа нужна строгая подпись кодом.

Что меняется по сути: для employee-подписи под флагом появляется **двухфазность** — сначала запрос (выдаётся код), затем подтверждение кодом. Только после подтверждения создаётся запись `BriefingSignature` (факт подписи). Attested-путь сохраняется как поведение по умолчанию (back-compat).

### Не-цели (отложено, Срез-4+)
- Доставка кода по SMS/email — код показывается в ответе API на `sign-employee` (единственная точка видимости, как для документов); показ/печать работнику — организационная процедура.
- Decline ознакомления самим работником (отказ подписать) — за срезом; ядро `decline` есть, briefing-обёртка не строится.
- Код-flow для instructor-подписи — инструктор аутентифицирован (залогинен), код избыточен; instructor остаётся attested.
- Resend-эндпоинт кода — после истечения TTL запрос становится `expired` (терминальный, не активный), и повторный `sign-employee` создаёт свежий запрос; отдельного resend не нужно.
- Печатная форма листа ознакомления.
- Фронтенд.

## 2. Архитектура

### 2.1 Что переиспользуется без изменений

ПЭП-ядро уже подготовлено к briefing глубже, чем фиксировал handoff:
- `domains/signing/pep.py` — FSM (`created→awaiting_code→signed/declined/expired`), `confirm_outcome` (порядок проверок TTL→код→счётчик), константы `MAX_CONFIRM_ATTEMPTS=5`, `CONFIRM_TTL_MINUTES=15`, `PEP_PURPOSES` (включает `"briefing"`).
- `services/pep_signing.py`:
  - `create_request(object_type, object_id, purpose, requested_by, signer_person_id=…)` → `(req, code)`; для person-подписанта выдаёт код, ставит `AWAITING_CODE`; dup-check по активным запросам `(object, purpose, signer)` (анти-двойная-выдача кода).
  - `confirm(request_id, code=…)` → на success `_mark_signed` (outbox `PEP_SIGNED`); контракт **commit-on-conflict** (при неверном/истёкшем/исчерпанном коде состояние запроса меняется → вызывающий обязан COMMIT).
  - `_build_content` уже обрабатывает `object_type == "briefing_entry"` (pep_signing.py:90–99).
  - `_dispatch_signed` для briefing **намеренно ничего не делает** (комментарий :370 «briefing: сама запись и есть результат») — ПЭП остаётся generic, briefing-запись создаёт briefing-модуль.

### 2.2 Что добавляется

| Где | Что |
|---|---|
| `models/models.py` `BriefingTemplate` | колонка `require_signature_code: bool` (default `false`) — зеркало существующего `validity_days` как политики типа инструктажа |
| миграция (head `med02`) | аддитивный `add_column briefing_templates.require_signature_code`; честный downgrade (`drop_column`); имена литералами |
| `modules/briefings/services.py` `BriefingEntryService` | ветка код-flow в `sign()` + новый `confirm_code()` |
| `api/routes/briefings.py` | ветвление ответа `sign-employee` + новый `POST /entries/{id}/confirm-code` |
| `schemas` briefing | модель pending-ответа + тело `confirm-code` |
| CRUD шаблонов | проброс `require_signature_code` в create/update схемы шаблона |
| `services/demo_bootstrap.py` | шаблон с `require_signature_code=true` + пример записи |

## 3. Триггер код-flow

Код-flow включается, когда **одновременно**:
1. `signer_type == "employee"`, И
2. `entry.person_id` задан (работник без учётки), И
3. шаблон записи (`entry.briefing_template_id`) существует и `template.require_signature_code is True`.

Иначе — attested-путь (текущее поведение, без изменений):
- instructor-подпись;
- employee без `person_id` (fallback за user-оформителем);
- запись без шаблона (`briefing_template_id is None`);
- шаблон с `require_signature_code == false`.

## 4. Поток

### 4.1 Фаза 1 — `POST /briefings/entries/{id}/sign-employee`

1. 404 если запись не найдена / не того тенанта (как сейчас).
2. existing-check (как сейчас): если подпись `employee` уже есть → возврат существующей (идемпотентность повторного вызова).
3. Вычислить `require_code` по триггеру §3 (загрузить шаблон, если есть `briefing_template_id`).
4. **Если `require_code`:**
   - `create_request(object_type="briefing_entry", object_id=entry.id, purpose="briefing", requested_by=signer_user_id or "system", signer_person_id=entry.person_id)` → `(req, code)`, статус `AWAITING_CODE`.
   - `BriefingSignature` **НЕ создаётся**; `entry.status` **НЕ меняется** (остаётся `draft`). Pending-состояние полностью живёт в `SignatureRequest`.
   - Ответ (pending-форма): `{entry, pending: {pep_request_id, status: "awaiting_code", confirm_code}}`. `confirm_code` виден только здесь.
   - dup-check `create_request` отбивает повторную выдачу кода активному запросу → `PepConflict` → **409**.
5. **Иначе** — attested-путь как сегодня: `create_attested` → строка `BriefingSignature` + `entry.status="signed_employee"` (контракт ответа прежний `{entry, signature}`).

### 4.2 Фаза 2 — `POST /briefings/entries/{id}/confirm-code` (новый)

Тело: `{code: str}`.

1. 404 если запись не найдена / не того тенанта.
2. `BriefingEntryService.confirm_code(session, entry, code)`:
   - найти единственный активный `AWAITING_CODE`-запрос по `(tenant, object_type="briefing_entry", object_id=entry.id, purpose="briefing", signer_person_id=entry.person_id)` (единственность гарантирует dup-check `create_request`); нет такого → **409** `no_pending_code_request` (или 404 — см. §6 решение контракта).
   - `PepSigningService.confirm(req.id, code=code)`:
     - неверный код → `PepConflict` (счётчик попыток +1);
     - истёкший → `PepConflict` (`expired`);
     - исчерпанный → `PepConflict` + запрос `declined`.
   - на success: создать `BriefingSignature` (`signer_type="employee"`, `signer_person_id=entry.person_id`, `signature_payload={pep_request_id: req.id}`), `entry.status="signed_employee"`; реюз хвоста `sign` с тем же IntegrityError→`BriefingSignatureConflict` guard.
3. **commit-on-conflict:** при `PepConflict` API-слой **коммитит** (не откатывает), затем кидает 409 — иначе инкремент попыток/переход в expired/declined теряются (бесконечный перебор кода). Контракт уже зафиксирован в `/sign/pep/requests/{id}/confirm`.
4. Ответ на success: `{entry, signature}` (как у attested-пути).

## 5. Инварианты и граничные случаи

- **Back-compat:** при `require_signature_code=false` (дефолт всех существующих и будущих шаблонов без явной установки) поведение `sign-employee`/`sign-instructor`/`complete` идентично текущему.
- **`briefing_signatures` = факт подписи:** строка создаётся только после подтверждения; pending-состояние — в `SignatureRequest`. Unique-индекс `uq_briefing_signatures_entry_signer` (ed03) по-прежнему охраняет финальную строку.
- **Анти-двойная-выдача:** `create_request` dup-check (активные статусы) не даёт выдать второй код тому же подписанту по той же записи → 409.
- **Истечение:** после TTL запрос `expired` (не активен) → повторный `sign-employee` создаёт новый запрос. Resend не нужен.
- **person_id=None при флаге on:** код невозможен (нет person) → attested fallback (консистентно с текущим fallback за оформителем).
- **Tenant-изоляция и ABAC:** прежние (write-роль на обоих эндпоинтах; `_build_content`/`confirm` проверяют tenant).
- **Аудит:** `confirm-code` логируется по образцу `sign_employee` (`audit_operation`).

## 6. Открытые мелочи контракта (решены)

- **Код ответа при отсутствии pending-запроса на confirm-code:** **409** `no_pending_code_request` (запись существует, но не в состоянии ожидания кода — конфликт состояния, не отсутствие ресурса). 404 зарезервирован за «запись не найдена».
- **`pep_request_id` в ответе sign-employee:** возвращается явно (диагностика/верификация через `/sign/pep/requests/{id}/verify`), хотя confirm-code ищет запрос сам по entry+person (клиенту не нужно его хранить).

## 7. Тестирование

**Сервис/домен:**
- confirm happy-path: верный код → `BriefingSignature` создана, `entry.status="signed_employee"`, ПЭП-запрос `signed`, outbox `PEP_SIGNED`.
- неверный код → 409, `confirm_attempts` инкремент **переживает коммит** (повторный неверный → счётчик растёт; после 5 → declined).
- истёкший код → 409 `expired`.
- флаг off / instructor / `person_id=None`+флаг on / нет шаблона → attested-путь, контракт прежний.
- повторный `sign-employee` при активном запросе → 409 (анти-двойная-выдача).
- existing-check: повторная подпись подтверждённого employee → возврат существующей.

**API:**
- `sign-employee` под флагом возвращает pending-форму с `confirm_code`; confirm-code финализирует.
- `confirm-code` без pending-запроса → 409.
- регрессия: instructor-подпись и `complete` (validity_days) не затронуты.

**Миграция:**
- single-head после `med02`; аддитивность; честный downgrade (drop column); guard-тест на цепочку и состав.

**Регрессия:** существующий briefing-когорт (`-k "briefing"`) зелёный; ПЭП-когорт зелёный.

## 8. Границы единиц (изоляция)

- **ПЭП-ядро** (`pep.py`/`pep_signing.py`) — не меняется; используется как generic-интерфейс. Вход: `create_request`/`confirm`. Зависимости: нет от briefing.
- **Briefing-модуль** (`BriefingEntryService`) — держит всю двухфазную логику и доменные правила (триггер, создание `BriefingSignature`, `entry.status`). Зависит от ПЭП-ядра через публичные методы.
- **API-слой** — ветвление ответа + commit-on-conflict + аудит. Зависит от briefing-сервиса.
- **Модель/миграция** — изолированная аддитивная колонка-политика.
