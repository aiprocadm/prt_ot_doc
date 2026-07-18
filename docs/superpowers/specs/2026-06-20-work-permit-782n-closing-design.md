# Дизайн: Наряд-допуск на высоте (782н) — Ф3b «закрытие наряда с подписями»

- **Дата:** 2026-06-20
- **Контур:** Наряды-допуски §16, эталон «работа на высоте» (Приказ Минтруда № 782н).
- **Этап:** Ф3b из программы Ф1→Ф4. **Влиты:** Ф1 (модель + экран, PR #669), Ф2 (целевой инструктаж + подписи ПЭП, PR #671), Ф3a (журнал эксплуатации: ежедневный допуск + продления + смена состава, PR #673/#674). Ф3b — **закрытие наряда с подписями** (расширяет Ф2). Ф4 — печатный бланк 782н.
- **Полнота стека:** Ф3b — **full-stack** (расширение модели наряда + переиспользование ПЭП-контура Ф2 + сервис + миграция + API + фронтенд). Без новой таблицы.
- **Ветка:** `feat/work-permits-782n-closing` (от `origin/main`, где Ф1/Ф2/Ф3a уже есть).
- **Источники:** [Приказ 782н — КонсультантПлюс](https://www.consultant.ru/document/cons_doc_LAW_371453/) — раздел «окончание работы и закрытие наряда-допуска»; ЭДО-ПЭП-контур (`domains/signing/pep.py`, `services/pep_signing.py`); Ф2-модуль подписи (`domains/work_permits/signing.py`).

## 1. Контекст и цель

После Ф1/Ф2/Ф3a наряд можно завести по форме, провести по FSM, провести инструктаж, собрать подписи и вести операционный журнал. Но **закрытие наряда фиктивно**: текущий `close` (`domains/work_permits/service.py:229`) просто ставит `status="closed"` + `closed_at` и пишет событие `closed` с опциональным фото/заметкой — **без акта окончания работ и без подписей сдачи-приёмки**.

По 782н закрытие наряда — это **акт сдачи-приёмки**: производитель работ заявляет окончание (работы окончены, рабочее место сдано/убрано, люди и инструмент выведены), а ответственный руководитель или допускающий принимает рабочее место. Обе стороны подписывают. Ф3b делает закрытие **юридически значимым**: акт окончания + две подписи ПЭП, гейтящие переход `issued→closed`.

**Центральное решение (гейт, а не отметка постфактум):** подпись закрытия — это и есть акт закрытия, поэтому подписи **блокируют** `close`, а не фиксируются на уже закрытом наряде. Это сознательно меняет контракт `close` из Ф1/Ф3a — в этом и состоит суть среза. (В Ф2 гейтинг FSM сознательно не вводился; Ф3b его вводит **только для `close`**.)

## 2. Объём

**В объёме (Ф3b):**
- Акт окончания работ — поля `completion_text` + `completion_recorded_at` на `work_permit` (аддитивная миграция `wp05`).
- Подписи закрытия двух классов через переиспользуемый Ф2-модуль `domains/work_permits/signing.py`, оба режима (`attested` / `code`): `object_type="work_permit_closing"`, `object_id=permit_id`.
- **Гейт перехода `issued→closed`**: требует оформленный акт + ≥1 SIGNED «сдал» + ≥1 SIGNED «принял».
- API: оформление акта, инициация/фиксация подписей закрытия, сводка закрытия (акт + подписи + готовность гейта). Гейтированный `close`.
- Frontend: новая панель `ClosingPanel` на карточке наряда (акт окончания + подписи «сдал/принял» + кнопка «Закрыть» с дизейблом и пояснением, пока гейт не готов).
- Обновление demo-seed и внутренних вызовов `close()` под новый контракт.
- Только роль `admin`.

**Вне объёма (следующие этапы):**
- Ф4: печатный бланк 782н (DOCX→PDF + фирменный бланк).
- Тиражирование на другие виды работ (902н/1479/903н…).
- Фото при закрытии вне существующего `photo_file_id` у события `closed` (мобильный экран — отдельно).
- Конфигурируемость гейта по тенанту (включать/выключать требование подписей) — гейт жёсткий по 782н.
- Гейтинг прочих переходов (`issue`/`suspend`/`cancel`) — `cancel` остаётся без гейта (отмена ≠ закрытие).

## 3. Аудитория и права

- Роль `admin` (специалист по ОТ). Backend `/work-permits` уже гейтит `required_roles=["admin"]` на чтение и запись.
- Фронтенд: переиспользуем коды Ф1/Ф2 — `work_permit.view` (просмотр панели закрытия) и `work_permit.manage` (оформление акта, инициация/фиксация подписей, закрытие). Новых кодов прав не вводим.

## 4. Модель данных (backend)

Закрытие наступает **ровно один раз** на наряд (1:1) → **без новой таблицы**; добавляем поля к существующему `work_permit`. Подписи **своей таблицы не получают** — живут в `signature_requests` (полиморфизм, как в Ф2).

Аддитивная миграция **`wp05`** (`20260620_wp05_work_permit_closing`, цепочка от истинного head — ожидается `20260618_wp04_work_permit_ops_journal`, проверить single-head в плане; имена таблиц литералами — [[audit_static_analysis_blindspots]]; honest downgrade удаляет добавленные колонки). Новые колонки у `work_permit`:

| Колонка | Тип | Назначение |
|---|---|---|
| `completion_text` | Text, null | акт окончания: работы окончены, рабочее место сдано/убрано, люди и инструмент выведены |
| `completion_recorded_at` | DateTime(timezone=True), null | когда оформлен акт окончания |

Существующие поля закрытия (`closed_at`, событие `closed` в `WorkPermitEvent`, опц. `photo_file_id`/`note`) переиспользуются без изменений. **VARCHAR/TEXT/DateTime, не PG-enum** — конвенция репо ([[enum_pg_label_parity]]).

## 5. ПЭП-интеграция (backend, переиспользование)

- `domains/signing/pep.py`: расширить `PEP_PURPOSES` значением `"work_permit_closing"` (сейчас содержит `work_permit`, `work_permit_briefing`).
- `services/pep_signing.py::_build_content` — новая ветка канонического снимка для хэша:
  - `object_type="work_permit_closing"` → `{work_permit_id, number, completion_text, completion_recorded_at, signer:{person_id, role}, status}` (детерминированный порядок ключей).
- Гейт одобрения `_approval_gate` не трогаем (бьёт только `document`) — закрытие подписывается свободно.
- Outbox-события `PEP_SIGNED` / `PEP_DECLINED` работают как есть (консьюмеры различают по `object_type`).

## 6. Сервис подписи закрытия (backend)

Расширяем Ф2-модуль `domains/work_permits/signing.py` функцией `sign_closing(session, *, tenant_id, permit_id, signer_person_id, role, mode, requested_by)`:

- `mode="attested"` → `create_attested(...)` (мгновенный SIGNED); `mode="code"` → `create_request(...)` (6-значный код подписанту).
- **Класс ролей закрытия:** подписант обязан быть `WorkPermitMember` наряда с ролью из `{foreman, supervisor, admitter}`. Иначе доменная ошибка → 4xx.
  - **«Сдал»** = `foreman` (производитель работ).
  - **«Принял»** = `supervisor` (ответственный руководитель) **или** `admitter` (допускающий).
- **Дубль-гард:** повторная активная/SIGNED-подпись для `(object_type="work_permit_closing", permit_id, signer_person_id)` запрещена (поверх существующего dup-check `create_request` + проверка отсутствия SIGNED).
- `confirm`/`decline` **не дублируем** — фронт вызывает существующий `/sign/pep/requests/{id}/confirm|decline`.

## 7. Гейт закрытия и сервис (backend)

Чистый предикат **`closing_readiness(permit, signatures) -> ClosingReadiness`** (в `domains/work_permits/lifecycle.py`, тестируемый изолированно):

- `act_recorded` = `completion_text` непуст;
- `has_handover` = есть ≥1 SIGNED-подпись с ролью подписанта `foreman`;
- `has_acceptance` = есть ≥1 SIGNED-подпись с ролью `supervisor` или `admitter`;
- `can_close` = `act_recorded and has_handover and has_acceptance`;
- `missing` = список недостающего (`completion_act` / `handover_signature` / `acceptance_signature`).

`close(...)` (в `service.py`) перед FSM-переходом вычисляет `closing_readiness`; если не `can_close` → доменная ошибка `WorkPermitClosingIncomplete` (несёт `missing`). Иначе — существующий переход (`status="closed"`, `closed_at`, событие `closed`).

Новый сервис-метод **`record_completion(session, *, tenant_id, permit_id, completion_text, actor_user_id)`** — идемпотентный upsert полей акта; разрешён в статусе `issued` (иначе доменная ошибка). Роль подписанта для предиката резолвится по `WorkPermitMember` наряда (person_id → role); если у наряда нет членов нужных ролей, гейт честно блокирует с понятным `missing`.

## 8. API (backend, на `routes/work_permits.py`)

Префикс `/api/v1/work-permits`, гейт `admin`, потолок списков `le=200` (как в Ф1).

- `POST /work-permits/{id}/closing` — оформить/обновить акт окончания: body `{completion_text}`; только в статусе `issued`; идемпотентный upsert.
- `GET /work-permits/{id}/closing` — сводка закрытия: `{completion_text, completion_recorded_at, signatures:[{request_id, person_id, fio, role, kind:"handover"|"acceptance", status}], can_close, missing}`.
- `POST /work-permits/{id}/closing/signatures` — инициировать/зафиксировать подпись закрытия: body `{person_id, role, mode}`; ответ — ПЭП read (+`confirm_code` для `mode="code"`).
- `POST /work-permits/{id}/close` (**существующий**) — теперь гейтит: `WorkPermitClosingIncomplete` → `409 WORK_PERMIT_CLOSING_INCOMPLETE` с `missing` в `details`.
- Подтверждение кода — через готовый `POST /sign/pep/requests/{id}/confirm`.

**Схемы** (`backend/app/schemas/`): `WorkPermitClosingRecord` (акт), `WorkPermitClosingSignatureCreate`, `WorkPermitClosingSummary` (сводка с `can_close`/`missing`). Для ответа подписи — переиспользовать существующую ПЭП-read-схему.

**Слом контракта `close` (обработка):** demo-seed (`_seed_*work_permit*`) и любые внутренние вызовы `close()` (в т.ч. в тестовых хелперах) обновляются: посев акта окончания + attested-подписей «сдал»/«принял» перед закрытием. Точечный аудит вызовов `close(` — задача плана.

## 9. Архитектура фронтенда (паттерн карточки Ф2 `SignaturesPanel`)

| Файл | Назначение |
|---|---|
| `frontend/src/api/workPermits.ts` | + `getClosing`, `recordCompletion`, `createClosingSignature` (+ переиспользовать `confirmSignatureCode` из Ф2). |
| `frontend/src/types/dto/workPermits.ts` | + `WorkPermitClosingSummaryDto`, `WorkPermitClosingSignatureDto`. |
| `frontend/src/lib/workPermitVocab.ts` | + подписи «сдал/принял» и недостающих пунктов гейта. |
| `frontend/src/features/work-permits/ClosingPanel.tsx` | акт окончания (форма, manage) + подписи «сдал/принял» со статусом и действиями attested/код+ввод кода + кнопка «Закрыть» **disabled с пояснением `missing`**, пока `can_close=false`. |
| `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` | + монтаж `ClosingPanel` (показывать для `issued`/`closed`). |
| тесты | `ClosingPanel.test.tsx`: статусы подписей, дизейбл «Закрыть» по `can_close`/`missing`, гейт действий по `work_permit.manage`. |

ФИО подписантов — резолв `person_id → ФИО` через `/persons` (как в Ф1/Ф2). Подход — api-модуль + `useAsyncResource`, без стора.

## 10. Поток закрытия

1. Наряд в `issued`, работы завершены. Admin оформляет **акт окончания** (`POST .../closing {completion_text}`).
2. Admin фиксирует подпись **«сдал»** (производитель работ, `foreman`) — attested или код.
3. Admin фиксирует подпись **«принял»** (`supervisor`/`admitter`) — attested или код.
4. Когда `can_close=true`, кнопка «Закрыть» активна → `POST .../close` → наряд `closed`.
5. Если admin жмёт «Закрыть» раньше (теоретически — кнопка дизейблена) → backend отвечает `409 WORK_PERMIT_CLOSING_INCOMPLETE` с `missing`.

**Code-режим:** ответ `closing/signatures {mode:"code"}` содержит `confirm_code` (показывается admin для передачи подписанту) → `POST /sign/pep/requests/{id}/confirm {code}` → SIGNED → панель reload. При ошибке кода (неверный/истёк/исчерпан) состояние запроса изменено → фронт делает reload.

## 11. Обработка ошибок

- Подписант не член бригады / неверный класс роли → 4xx + понятный `toast`.
- Повторная подпись (уже есть активная/SIGNED) → 409 + `toast`.
- Акт оформляется не в `issued` → 409 + `toast`.
- `close` без готового гейта → 409 `WORK_PERMIT_CLOSING_INCOMPLETE` (+ `missing` в `details`); фронт показывает причину.
- 404 (наряд удалён параллельно) → `toast` + reload/возврат.
- Код неверный/истёк/исчерпан → 409 (фронт: `toast` + reload статуса).
- Загрузка панели упала → `ErrorState` + «Повторить»; пусто → `EmptyState`.

## 12. Тестирование

- **Backend домен:** `PEP_PURPOSES` содержит `work_permit_closing`; стабильность канонического снимка closing (детерминированный хэш); `closing_readiness` — матрица (нет акта / нет «сдал» / нет «принял» / всё есть → can_close).
- **Миграция `wp05` (guard):** цепочка от истинного head (single-head); состав новых колонок `work_permit`; honest downgrade удаляет добавленное.
- **Сервис:** `record_completion` (upsert, отказ вне `issued`); attested/code подпись закрытия; валидация членства (чужой person / неверная роль → ошибка); дубль-гард; **гейт: `close` без подписей → `WorkPermitClosingIncomplete`; с актом+сдал+принял → успех**; `cancel` без гейта проходит.
- **API:** closing act create→read; signatures attested → `GET /closing` показывает SIGNED + `can_close`; code-flow → возвращает код, confirm через ПЭП-эндпоинт → SIGNED; `close` 409 без гейта → 200 после; tenant-isolation (cross-tenant 404/no-leak); подписант-не-член → 4xx.
- **Frontend:** `ClosingPanel` — отображение статусов «сдал/принял»; кнопка «Закрыть» disabled пока `can_close=false` с пояснением `missing`; гейт действий по `work_permit.manage`.
- **Регрессия слома `close`:** обновлённый demo-seed закрывает наряд по новому контракту; затронутые тесты Ф1/Ф3a, вызывающие `close()`, посеяны под гейт и зелёные.
- Прогон: Py3.12 если доступен, иначе доступный Python с отметкой о версии (CLAUDE.md). Frontend: `npm --prefix frontend run test -- <file>` + `build`.

## 13. Критерии приёмки

1. Миграция `wp05` аддитивна, downgrade честный; guard зелёный; single-head.
2. Акт окончания оформляется/правится/читается; только в `issued`; идемпотентно.
3. Подписи закрытия обоих классов работают в обоих режимах; невалидный подписант/повтор → 4xx; `verify()` даёт корректный хэш.
4. `close` гейтится: без акта+сдал+принял → 409 `WORK_PERMIT_CLOSING_INCOMPLETE`; с полным набором → `closed`. `cancel` не затронут.
5. `GET /closing` отдаёт акт + подписи (ФИО+роль+kind) + `can_close`/`missing`; доступ только admin.
6. Карточка показывает прогресс закрытия; кнопка «Закрыть» дизейблится с пояснением; действия admin-only.
7. demo-seed и затронутые тесты обновлены под новый контракт; backend-контур + фронт-тест зелёные; сборка фронта без ошибок типов/линта.

## 14. Открытые вопросы

Нет. Акт закрытия — 1:1, поля на наряде (без отдельной таблицы); подписи — полиморфная привязка в `signature_requests` (`object_type="work_permit_closing"`); гейт жёсткий по 782н и распространяется только на `close`; слом контракта `close` обрабатывается обновлением demo-seed и затронутых вызовов.
