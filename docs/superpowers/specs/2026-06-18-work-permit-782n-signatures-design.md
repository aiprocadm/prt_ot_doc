# Дизайн: Наряд-допуск на высоте (782н) — Ф2 «целевой инструктаж + подписи ПЭП»

- **Дата:** 2026-06-18
- **Контур:** Наряды-допуски §16, эталон «работа на высоте» (Приказ Минтруда № 782н).
- **Этап:** Ф2 из программы Ф1→Ф4. Ф1 (модель + экран) **влит** (PR #669, merged 2026-06-18). Ф2 — целевой инструктаж + подписи членов бригады и ответственных лиц (ПЭП). Ф3 — ежедневный допуск / журнал продлений / смена состава / закрытие с подписями. Ф4 — печатный бланк 782н.
- **Полнота стека:** Ф2 — **full-stack** (новая модель инструктажа + ПЭП-интеграция + сервис + миграция + API + фронтенд). Переиспользует готовый ЭДО-ПЭП-контур, не дублирует его.
- **Ветка:** `feat/work-permits-782n-signatures` (от `origin/main` b269116, где Ф1 уже есть).
- **Источники:** [Приказ 782н — КонсультантПлюс](https://www.consultant.ru/document/cons_doc_LAW_371453/); ЭДО-ПЭП-контур платформы (`domains/signing/pep.py`, `services/pep_signing.py`, образец — `modules/briefings`).

## 1. Контекст и цель

После Ф1 наряд можно завести «по форме» 782н и провести по FSM (`draft→issued→suspended↔issued→closed/cancelled`), но он **не имеет юридической значимости**: нет подписей и нет фиксации целевого инструктажа. Ф2 добавляет два юридически разных потока 782н:

1. **Подпись наряда** ответственными лицами (выдающий, ответственный руководитель, допускающий, производитель работ).
2. **Целевой инструктаж** бригады с **ознакомлением** (подписью) членов бригады.

Обе подписи — **ПЭП** (простая электронная подпись) поверх существующего контура. Юр-значимость держится на `SignatureRequest.content_hash` (SHA-256 канонического снимка объекта) + `verify()` + outbox-события `PEP_SIGNED`/`PEP_DECLINED`.

## 2. Объём

**В объёме (Ф2):**
- Новая лёгкая сущность **целевого инструктажа** `work_permit_briefing`, привязанная к наряду (кто провёл, когда, темы).
- ПЭП-подписи **двух потоков** через готовый `PepSigningService`: ответственные → наряд (`object_type="work_permit"`); члены бригады → инструктаж (`object_type="work_permit_briefing"`).
- **Оба режима подписи**: `attested` («при оформителе», мгновенный SIGNED) и `code` (OTP-код подписанту → подтверждение).
- API: CRUD инструктажа, создание подписей обоих потоков, список подписей со статусом. Подтверждение/отзыв кода — через **существующий** ручной эндпоинт `/sign/pep/requests/{id}/confirm|decline`.
- Frontend: две новые панели на карточке наряда (инструктаж + подписи), отображение прогресса, действия admin-only.
- Только роль `admin`.

**Вне объёма (следующие этапы):**
- **Гейтинг FSM не меняется** (сознательное решение): подписи и инструктаж **фиксируются и показываются**, но не блокируют «Выдать»/прочие действия. Контракт действий Ф1 нетронут.
- Ф3: ежедневный допуск (таблица), журнал продлений, смена состава, закрытие с подписями.
- Ф4: печатный бланк 782н.
- Фото при подписи/инструктаже (мобильный экран — отдельно).
- Тиражирование на другие виды работ.
- Самоподпись через `signer_user_id` (в Ф2 все подписанты — это `Person` членов бригады; оформитель = `requested_by`).

## 3. Аудитория и права

- Роль `admin` (специалист по ОТ). Backend `/work-permits` уже гейтит `required_roles=["admin"]`.
- Фронтенд: переиспользуем коды Ф1 — `work_permit.view` (просмотр панелей), `work_permit.manage` (проведение инструктажа, инициация/фиксация подписей). Новых кодов прав не вводим.

## 4. Модель данных (backend)

Аддитивная миграция **`wp03`** (цепочка от истинного head — определить в плане, ожидается `wp02`; имена таблиц литералами; honest downgrade удаляет добавленное). Подписи **не** получают своей таблицы — живут в существующем `signature_requests`.

**Новая таблица `work_permit_briefing`** (модель `WorkPermitBriefing`, `backend/app/models/work_permit.py`, базовый `TenantBaseModel`):

| Колонка | Тип | Назначение |
|---|---|---|
| `work_permit_id` | FK→`work_permit.id` (CASCADE), not null, index | наряд |
| `conducted_by_person_id` | FK→`person.id` (SET NULL), null | кто провёл (обычно производитель работ) |
| `conducted_at` | DateTime(tz), null | когда проведён |
| `topics_text` | Text, null | темы/содержание инструктажа |

Связь **1:N** (наряд → инструктажи[]) — задел под Ф3 (ежедневные); Ф2 ведёт один «целевой» инструктаж на наряд (UI создаёт/показывает текущий). Базовые `id/tenant_id/created_at/updated_at` — из `TenantBaseModel`.

## 5. ПЭП-интеграция (backend, переиспользование)

- `backend/app/domains/signing/pep.py`: расширить `PEP_PURPOSES` значениями `"work_permit"` и `"work_permit_briefing"`.
- `backend/app/services/pep_signing.py::_build_content` — две новые ветки (канонический снимок для хэша):
  - `object_type="work_permit"` → `{number, work_type, zone_text, секции 782н, members:[{person_id, role}], status}`;
  - `object_type="work_permit_briefing"` → `{work_permit_id, conducted_by_person_id, conducted_at, topics_text, members:[...]}`.
- Гейт одобрения `_approval_gate` остаётся прежним (бьёт только `document`) — наряд/инструктаж подписываются свободно.
- Outbox-события `PEP_SIGNED`/`PEP_DECLINED` работают как есть (консьюмеры смогут слушать по `object_type`).

## 6. Сервис подписи наряда (backend)

Новый тонкий модуль `backend/app/domains/work_permits/signing.py` поверх `PepSigningService` (образец — `modules/briefings/services.py`):

- `sign_permit(session, tenant_id, permit_id, signer_person_id, role, mode, requested_by)` и `sign_briefing(session, tenant_id, briefing_id, signer_person_id, mode, requested_by)`:
  - `mode="attested"` → `create_attested(...)` (мгновенный SIGNED);
  - `mode="code"` → `create_request(...)` (вернёт 6-значный код подписанту).
- **Валидация членства:** подписант обязан быть `WorkPermitMember` соответствующего класса ролей —
  - наряд: ответственные `{issuer, supervisor, admitter, foreman}`;
  - инструктаж: бригада `{member, observer, foreman}`.
  Иначе доменная ошибка → 409/422.
- **Дубль-гард:** повторная активная/SIGNED-подпись для `(object_type, object_id, signer_person_id)` запрещена (поверх существующего dup-check `create_request` + проверка отсутствия SIGNED).
- `confirm`/`decline` **не дублируем** — фронт вызывает существующий `/sign/pep/requests/{id}/confirm|decline`.

## 7. API (backend, на `routes/work_permits.py`)

Префикс `/api/v1/work-permits`, гейт `admin`, потолок списков `le=200` (как в Ф1).

- `POST /work-permits/{id}/briefing` — провести/создать целевой инструктаж (`conducted_by_person_id?`, `conducted_at?`, `topics_text?`).
- `GET /work-permits/{id}/briefing` — инструктаж(и) наряда.
- `PATCH /work-permits/{id}/briefing/{bid}` — правка инструктажа.
- `POST /work-permits/{id}/signatures` — инициировать/зафиксировать подпись ответственного: body `{person_id, role, mode}`; ответ — `SignatureRequest`-read (+ `confirm_code` для `mode="code"`).
- `POST /work-permits/{id}/briefing/{bid}/signatures` — подпись-ознакомление члена бригады: body `{person_id, mode}`.
- `GET /work-permits/{id}/signatures` — список подписей **обоих потоков** со статусом, типом, ФИО+ролью (резолв `person_id`).
- Подтверждение кода — через готовый `POST /sign/pep/requests/{id}/confirm`.

**Схемы** (`backend/app/schemas/`): `WorkPermitBriefingCreate/Update/Read`, `WorkPermitSignatureCreate`; для ответа подписи переиспользовать существующую ПЭП-read-схему (`SignatureRequest`).

## 8. Архитектура фронтенда (паттерн карточки Ф1)

| Файл | Назначение |
|---|---|
| `frontend/src/api/workPermits.ts` | + `getBriefing/createBriefing/updateBriefing`, `listSignatures/createPermitSignature/createBriefingSignature`, `confirmSignatureCode` (→ `/sign/pep/...`). |
| `frontend/src/types/dto/workPermits.ts` | + `WorkPermitBriefingDto`, `WorkPermitSignatureDto`. |
| `frontend/src/lib/workPermitVocab.ts` | + подписи режимов/статусов подписи. |
| `frontend/src/features/work-permits/BriefingPanel.tsx` | целевой инструктаж: запись (кто/когда/темы) + форма «Провести инструктаж» (manage) + список бригады со статусом ознакомления и действиями. |
| `frontend/src/features/work-permits/SignaturesPanel.tsx` | подписи ответственных: роли со статусом + действия «Зафиксировать подпись» (attested) / «Запросить код» + ввод кода. |
| `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` | + монтаж двух панелей. |
| тесты | `SignaturesPanel.test.tsx` (или расширение `WorkPermitDetailPage.test.tsx`): статусы подписей + гейт действий по `work_permit.manage`. |

ФИО подписантов — резолв `person_id → ФИО` через `/persons` (как в Ф1). Подход — api-модуль + `useAsyncResource`, без стора.

## 9. Поток подписи (оба режима)

- **attested:** admin жмёт «Зафиксировать подпись» у участника → `POST .../signatures {mode:"attested"}` → сразу SIGNED, в `result_json` фиксируется `attested_by`. UI обновляет статус.
- **code:** admin жмёт «Запросить код» → `POST .../signatures {mode:"code"}` → ответ содержит `confirm_code` (показывается admin для передачи подписанту) → подписант/admin вводит код → `POST /sign/pep/requests/{id}/confirm {code}` → SIGNED. Контракт ПЭП: при ошибке кода (неверный/истёк/исчерпан) состояние запроса **изменено** → фронт делает reload.

## 10. Обработка ошибок

- Подписант не член бригады / неверный класс роли → 409/422 + понятный `toast`.
- Повторная подпись (уже есть активная/SIGNED) → 409 + `toast`.
- 404 (наряд/инструктаж удалён параллельно) → `toast` + reload/возврат.
- Код неверный/истёк/исчерпан → 409 (фронт: `toast` + reload статуса).
- Загрузка панели упала → `ErrorState` + «Повторить»; пусто → `EmptyState`.

## 11. Тестирование

- **Backend домен:** `PEP_PURPOSES` содержит новые значения; стабильность канонического снимка наряда/инструктажа (детерминированный хэш).
- **Миграция `wp03` (guard):** цепочка от истинного head; состав колонок `work_permit_briefing`; honest downgrade удаляет таблицу.
- **Сервис:** создание инструктажа; attested-подпись наряда и инструктажа; code-flow `create_request`→`confirm`; валидация членства (чужой person → ошибка); дубль-гард (второй SIGNED запрещён).
- **API:** briefing create→read→patch; attested signature → `GET /signatures` показывает SIGNED; code-flow → возвращает код, confirm через ПЭП-эндпоинт → SIGNED; tenant-isolation (cross-tenant 404/no-leak); подписант-не-член → 4xx.
- **Frontend:** панель подписей — отображение статусов; гейт действий по `work_permit.manage`.
- Прогон: Py3.12 если доступен, иначе доступный Python с отметкой о версии (CLAUDE.md). Frontend: `npm --prefix frontend run test -- <file>` + `build`.

## 12. Критерии приёмки

1. Миграция `wp03` аддитивна, downgrade честный; guard зелёный.
2. Целевой инструктаж заводится/правится/читается; привязан к наряду (1:N).
3. Подписи обоих потоков работают в обоих режимах; невалидный подписант/повтор → 4xx; `verify()` даёт корректный хэш.
4. `GET /signatures` отдаёт статус обоих потоков с ФИО+ролью; доступ только admin.
5. Карточка показывает прогресс инструктажа и подписей; действия admin-only; **FSM Ф1 не изменён**.
6. Тесты (backend-контур + фронт-тест) зелёные; сборка фронта без ошибок типов/линта.

## 13. Открытые вопросы

Нет. Целевой инструктаж — лёгкая сущность 1:N под Ф3-задел; подписи — прямая полиморфная привязка в `SignatureRequest` (без промежуточной таблицы); гейтинг FSM сознательно не вводится в Ф2.
