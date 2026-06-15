# ЭДО Срез-1: ПЭП внутренний контур — дизайн

**Дата:** 2026-06-11
**Контур:** ЭДО / подпись (ТЗ раздел B.5, vNext §6.9 «ПЭП для внутреннего контура», §6.10 «история ознакомлений»)
**Ветка:** `feat/edo-pep-signing`
**Статус до среза:** контур ЭДО ~30% — движок согласования (approvals v2) рабочий ~70%; подпись ~10% (INTERNAL ставится мгновенно без фиксации содержимого, `MockSignatureProvider`); ЭДО-оператор ~5% (`/edo/send` рисует фейковые статусы через `edo_status_simulation_job`); интеграция согласовано→подпись→ЭДО разорвана (0%).
**Статус после среза:** ✅ РЕАЛИЗОВАНО И ВЛИТО — PR #649 (`974cd30`) + чистка PR #650 (`a006d6e`). Построены: чистый домен `domains/signing/pep.py` (FSM, канонизация payload, SHA-256 кода, верификация), сервис `PepSigningService`, миграция `ed01`, роуты `/sign/pep/*` + `/sign/acknowledgements`, потребители (докфабрика/СИЗ/инструктажи/ознакомления), outbox-события `PEP_SIGNED`/`PEP_DECLINED`, unit+API тесты; симуляция (`MockSignatureProvider`, `MockEdoOperator`, `edo_status_simulation_job`) вычищена честно, КЭП/УНЭП → 409. Проверено аудитом кода 2026-06-15.

## 1. Цель среза

Сделать **по-настоящему рабочую простую электронную подпись (ПЭП)** для внутреннего контура и подключить к ней трёх потребителей. Реальная интеграция с внешним оператором (КЭП/УНЭП) невозможна без учётки оператора — она остаётся за срезом, а её симуляция **вычищается честно**.

Рабочая ПЭП означает:
- фиксируется **ЧТО** подписано — SHA-256 от канонического представления содержимого;
- фиксируется **кто/когда** — user или person, снапшот ФИО, timestamp;
- подписант-сотрудник без учётки подтверждает подпись **разовым кодом**;
- подпись можно **верифицировать** — пересчёт hash по текущему объекту, протокол проверки сохраняется;
- всё видно в **журнале**.

### Не-цели (отложено, Срез-2+)
- Интеграция с реальным оператором ЭДО (КЭП/УНЭП/МЧД, роуминг, квитанции, входящие).
- Доставка кода подтверждения по SMS/email — в Срезе-1 код показывается оформителю в ответе API (показ/печать сотруднику — организационная процедура).
- Код-flow для briefing-подписей (в Срезе-1 briefing идёт как attested-подпись оформителя).
- Печатная форма МБ-7 (СИЗ) и печатная форма листа ознакомления.
- Оживление `PackRun.signature_status/edo_status`; автозапуск подписания после согласования (оркестрация §6.5).
- Фронтенд (EdoPage/SignaturesPage уже показывают non-production note; контракт честных ошибок им подходит).
- DROP легаси-таблиц `signatures` (v1), `edo_envelopes`.

## 2. Архитектура

### 2.1 Чистый домен `backend/app/domains/signing/`

По образцу `domains/ppe/lifecycle.py` — чистые функции без I/O:

- `canonical_payload(object_type, object_id, content: dict) -> str` — канонический JSON (sorted keys, ensure_ascii=False, компактные разделители). Состав `content` по типу объекта:
  - `document_version`: id версии, номер версии, hash/ссылка содержимого файла;
  - `ppe_issue`: id выдачи, item (id+name), qty, даты, тип операции;
  - `briefing_entry`: id записи, template/тема, person, дата.
- `content_hash(payload: str) -> str` — SHA-256 hex.
- FSM: `created → awaiting_code → signed | declined | expired` (+ легаси `requested/failed` у старых строк). Допустимые переходы валидируются чистой функцией (`InvalidTransition` по образцу PPE FSM).
- Код подтверждения: 6 цифр; в БД — только SHA-256(code + request_id) (соль = id запроса); TTL 15 минут; максимум 5 попыток, после — `declined` c `reason=attempts_exhausted`. Генерация secrets.randbelow.
- Подписант-**user**: подтверждение аутентифицированным действием, код не нужен. Если подписант == оформитель — `created → signed` в момент создания; если другой user — запрос остаётся в `created`, подписант подтверждает через `/confirm` **без кода** (проверка: текущий user == `signer_user_id`).
- Подписант-**person** (без учётки): `created → awaiting_code` → ввод кода → `signed`.
- `expired` проставляется **лениво** — при попытке confirm с истёкшим TTL; отдельного beat-job нет.

### 2.2 Сервис `services/pep_signing.py` (session-aware)

Оркеструет: построение payload по типу объекта (загрузка объекта, проверка tenant), создание/подтверждение/отклонение запроса, верификацию, диспетчер потребителей на `signed` (см. §5), регистрацию outbox-событий.

## 3. Данные — миграция `ed01`

`20260611_ed01_pep_signing` (цепочка `sz02 → ed01`), **аддитивная** к `signature_requests`:

| Колонка | Тип | Назначение |
|---|---|---|
| `signer_person_id` | String(36), FK `person.id` ON DELETE SET NULL, index | подписант-сотрудник |
| `content_hash` | String(64), nullable | SHA-256 канонического payload |
| `purpose` | String(32), nullable (новые строки — обязательно) | `document` / `acknowledgement` / `ppe_issue` / `briefing` |
| `confirm_code_hash` | String(64), nullable | hash разового кода |
| `confirm_code_expires_at` | DateTime(tz), nullable | TTL кода |
| `confirm_attempts` | Integer, default 0 | счётчик неверных вводов |

Плюс: `status` VARCHAR(16) → VARCHAR(32) (additive-safe widening; новые значения `awaiting_code/declined/expired`). Новые строки — `signature_type='pep'`, `provider='internal'`. **VARCHAR, не PG-enum** (уроки #635–#638). Существующие индексы `(tenant, object_type, object_id[, status])` достаточны.

Downgrade: дроп колонок + сужение status обратно (с честным фейлом, если есть значения длиннее 16 — по образцу sz01).

`signatures` (v1) и `briefing_signatures` не дропаются: v1 перестаёт получать новые записи, briefing-таблица остаётся доменной проекцией (новые строки получают `pep_request_id` внутри `signature_payload` JSON — без миграции схемы).

## 4. API (расширение роутера `/sign`)

| Эндпоинт | Метод | Поведение |
|---|---|---|
| `/sign/pep/requests` | POST | `{object_type, object_id, purpose, signer_user_id \| signer_person_id}`. Оформитель = текущий user (`requested_by`). Если подписант-user == текущий user → мгновенный `signed`. Если person → `awaiting_code`, в ответе **разовый код** (единственный момент видимости). Валидации: объект существует и в тенанте (404), гейт согласования для `purpose='document'` (409 `approval_required`), дубль активного запроса на тот же объект+подписант+purpose (409). |
| `/sign/pep/requests/{id}/confirm` | POST | `{code?}` → `signed` (фиксация `signed_at`, `signer_name` снапшот ФИО). Person-подписант: код обязателен; 409 — неверный код (+attempt), истёкший (`expired`), исчерпание попыток (`declined`). User-подписант: без кода, но текущий user обязан совпадать с `signer_user_id` (иначе 403). |
| `/sign/pep/requests/{id}/decline` | POST | `{reason?}` → `declined` (из `created/awaiting_code`). |
| `/sign/pep/requests` | GET | журнал: фильтры `object_type`, `object_id`, `signer_person_id`, `status`, `purpose`. |
| `/sign/pep/requests/{id}/verify` | GET | пересчёт канонического hash по текущему объекту, сравнение с `content_hash`; протокол проверки пишется в `verification_result_json` (vNext §6.9 «хранение протоколов проверки подписи»). |
| `/sign/acknowledgements` | GET | история ознакомлений (§6.10): фильтры `document_version_id`, `person_id` — выборка `purpose='acknowledgement'`. |

ABAC/роли — по образцу существующих write-ролей контура documents; tenant-isolation как везде. Код в ответах никогда не логируется и не возвращается повторно.

## 5. Потребители (диспетчер на `signed`)

1. **Докфабрика (`purpose='document'`):** гейт — если по `document_version` есть `ApprovalInstance`, он должен быть `APPROVED`, иначе 409 `approval_required`; если маршрута нет — подпись разрешена. На `signed` → `DocumentVersion.signature_status='signed'` (оживление мёртвой проекции).
2. **СИЗ МБ-7 (`purpose='ppe_issue'`):** на `signed` → `PPEIssue.signature_doc_ref = "pep:<request_id>"`. Generic-эндпоинт, отдельный PPE-роут не нужен.
3. **Ознакомления (`purpose='acknowledgement'`):** person × document_version; материализуется только записью в `signature_requests` + читается через `/sign/acknowledgements`.
4. **Briefings (`purpose='briefing'`):** `BriefingEntryService.sign` создаёт через ядро attested-ПЭП-запись (мгновенный `signed`): для `signer_type='instructor'` подписант — `signer_user_id` из payload; для `signer_type='employee'` подписант-person — `entry.person_id`. `pep_request_id` кладётся в `signature_payload`. **Контракт briefing-эндпоинтов не меняется**; старые строки `briefing_signatures` — валидная история.

## 6. Чистка симуляции (честно)

- `edo_status_simulation_job` — **удаляется** (вместе с вызовами из `/edo/send`).
- `/edo/send` → 409 `edo_provider_not_configured` (честная ошибка вместо фейкового SENT). `send_edo_job`-заглушка удаляется.
- `MockEdoOperator`, `MockSignatureProvider` — удаляются; refresh/verify эндпоинты v1, ходившие в мок, возвращают 409 `signature_provider_not_configured` для не-PEP типов.
- `POST /signatures` (v1): `type=INTERNAL` → роутится через ПЭП-ядро (honest hash + journal, ответ сохраняет контракт v1); `KEP/UNEP` → 409 `signature_provider_not_configured`. Новые записи в таблицу `signatures` не пишутся.

## 7. События

Регистрация в outbox-пайплайне (по образцу СИЗ Среза-1: `_PAYLOADS`, `dedupe_key_for`, `_pipeline_for_event`):
- `sign.pep.signed` — payload: request_id, object_type/object_id, purpose, signer;
- `sign.pep.declined` — payload: request_id, reason.

## 8. Тесты

- **Unit ядра:** канонизация (стабильность сортировки/юникод), hash, FSM-переходы (валидные/невалидные), TTL и счётчик попыток кода.
- **API-интеграция:** полный цикл person-подписанта (create → код → confirm → signed); 5 неверных кодов → declined; истёкший код → expired; user-подписант мгновенный signed; дубль активного запроса → 409; decline.
- **Гейт согласования:** документ с не-APPROVED инстансом → 409; без маршрута → разрешено; APPROVED → signed + `DocumentVersion.signature_status='signed'`.
- **СИЗ:** на signed `signature_doc_ref="pep:<id>"` проставлен.
- **Briefings parity:** контракт sign-employee/sign-instructor прежний + появляется ПЭП-запись с `purpose='briefing'`.
- **Чистка:** `/edo/send` → 409; KEP/UNEP → 409; симуляционный job отсутствует в реестре задач.
- **Миграция:** guard-тест `ed01` (цепочка, состав колонок, widening status, downgrade round-trip).
- **Tenant-isolation:** чужой тенант не видит/не подтверждает запрос.
- **Верификация:** verify после изменения объекта → mismatch в протоколе.

## 9. Риски и решения

- **Юридическая сила ПЭП** требует организационного соглашения с сотрудниками (62-ФЗ) — платформа фиксирует технический след (hash, код, timestamp); текст соглашения — вне платформы.
- **Код виден оформителю** в ответе создания запроса — компромисс Среза-1 (доставка по SMS/email отложена). Код одноразовый, TTL 15 мин, hash-хранение.
- **Расширение status до VARCHAR(32)** затрагивает существующие строки только типом колонки — данные не переписываются.
- **`/signatures` v1 contract:** INTERNAL-ответ сохраняет форму, но семантика честнее (hash вместо мгновенной заглушки); фронтенд `sign.ts` использует `/sign/requests` — список продолжает работать (читает ту же таблицу).
