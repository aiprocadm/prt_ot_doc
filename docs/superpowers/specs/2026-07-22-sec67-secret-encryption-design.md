# SEC-67 — Единая политика секретов: шифрование HMAC-секретов вебхуков at rest — design spec

- **Дата:** 2026-07-22
- **Статус:** approved (пункт выбран пользователем через AskUserQuestion; scope + схема — стандартные, ниже)
- **Ветка:** `feat/sec67-secrets-encryption` от `main` (после мержа PR #779 RLS-гарда).
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B-NEXT.7 → «Единая политика секретов (шифрование, ротация) — разд. 67». Матрица SEC-67 (`partial(token-hash+tenant-key-enc)` → `partial(+webhook-secret-enc)`).
- **Аддитивно:** новых таблиц/миграций НЕТ. Формат хранения обратно-совместим (старый открытый текст продолжает читаться), поэтому бэкфилл не требуется.

## 1. Контекст (сверка код↔ТЗ)

Пароли (`hashed_password`) и API-токены (`token_hash`) уже **хешируются** (односторонне) — их трогать не надо. **Дыра:** HMAC-секреты вебхуков хранятся в БД **открытым текстом**:
- `webhook_endpoints.secret` (`WebhookEndpoint.secret`, `models/approval_runtime.py`),
- `webhook_subscription.secret` (`WebhookSubscription.secret`, `models/tenant_billing.py`).
Эти секреты — симметричные (нужны в исходном виде для подписи payload, `services/webhooks.py::_deliver` → HMAC-SHA256), поэтому хеш не подходит — нужно обратимое **шифрование at rest**. При утечке дампа/бэкапа злоумышленник иначе получит секреты и сможет подделывать подписанные вебхуки.

Симметричной криптографии в проекте нет (только RSA для JWT). `TenantIntegrationKey.encrypted_secret` — «зашифрован» лишь по названию, в коде не расшифровывается (счётчик готовности) — **вне объёма** этого среза.

## 2. Решения (стандартные, зафиксированы в дизайне)

1. **Схема — AES-256-GCM** (`cryptography.hazmat...AESGCM`, уже в зависимостях): AEAD, nonce на каждое шифрование, тег целостности. Мастер-ключ 32 байта.
2. **Мастер-ключ** — env `APP_SECRET_ENCRYPTION_KEY` (base64/hex 32 байта). В `production`/`staging` **обязателен** (иначе `encrypt_secret` кидает — fail-closed, шифрование без ключа бессмысленно). В `development`/`test` при отсутствии — **детерминированный dev-ключ** из `SECRET_KEY` (`sha256(secret_key + "webhook-secret-v1")[:32]`), по образцу «bundled dev RSA key» для JWT — чтобы тесты/локалка работали без конфигурации.
3. **Формат хранения** `enc:v1:<b64(nonce(12) + ciphertext + tag)>`. `decrypt_secret`: префикс есть → расшифровать; **нет префикса → вернуть как есть** (легаси-открытый текст читается). `encrypt_secret`: всегда выдаёт префиксный шифротекст. → **бэкфилл не нужен**; старые секреты шифруются лениво при ротации.

## 3. Не-цели (вне объёма)

- Бэкфилл-шифрование существующих открытых секретов (лениво при ротации; опц. management-команда — отдельно).
- `TenantIntegrationKey.encrypted_secret` (не используется активно), SMTP/Telegram/интеграционные токены из **env-настроек** (не в БД пер-тенант).
- Ротация мастер-ключа / несколько версий ключей (формат `v1` заложен на будущее, но key-rotation — отдельный срез).
- KMS/HSM (env-ключ; интеграция с секрет-хранилищем — инфра-решение).

## 4. Backend — крипто-модуль

**Новый** `backend/app/core/secret_cipher.py`:
- `class SecretDecryptError(ValueError)`.
- `_master_key(settings) -> bytes` — из `settings.secret_encryption_key` (base64/hex→32b), иначе dev-производный (только не-prod/staging), иначе (prod без ключа) — `RuntimeError` при попытке шифрования.
- `encrypt_secret(plaintext: str, *, settings=None) -> str` → `enc:v1:<b64>`.
- `decrypt_secret(stored: str | None, *, settings=None) -> str | None` — префикс → AESGCM.decrypt; иначе passthrough (легаси); `None`→`None`. Ошибка расшифровки → `SecretDecryptError`.
- `is_encrypted(value) -> bool`.

**Settings** (`config.py`): `secret_encryption_key: str = Field("", alias="APP_SECRET_ENCRYPTION_KEY")`.

## 5. Backend — врезка (encrypt-on-write / decrypt-on-read)

- **Запись** (`api/routes/webhooks.py`): при создании (`secret=generated_secret`), обновлении (`row.secret = payload.secret or ...`), ротации (`row.secret = new_secret`) — хранить `encrypt_secret(<plaintext>)`. **API-ответ отдаёт ОТКРЫТЫЙ** `generated_secret`/`new_secret` (как сейчас — секрет показывается один раз при создании/ротации), в БД — шифротекст.
- **Чтение** (`services/webhooks.py`): при сборке `WebhookDestination` из `row.secret`/`sub.secret` (строки ~172/202/275) — `decrypt_secret(...)`, чтобы HMAC подписывался исходным секретом. Легаси-открытые секреты расшифровка вернёт как есть → подпись не ломается в переходный период.

## 6. Frontend / demo-seed

Фронта нет. Демо-сид вебхук-секреты не сидит (или сидит открытым — расшифровка-passthrough вернёт как есть). Не трогаем.

## 7. Тест-план

**Unit** `tests/test_secret_cipher.py` (НОВЫЙ, без БД): round-trip encrypt→decrypt; префикс `enc:v1:`; легаси-passthrough (открытый текст без префикса → как есть); `None`→`None`; разные nonce на два шифрования одного текста (не детерминировано); порча шифротекста → `SecretDecryptError`; prod без ключа → `RuntimeError` на encrypt; dev без ключа → работает (dev-ключ).

**API/service** (расширить/новый): создание вебхука → в БД `row.secret` начинается с `enc:v1:` (не равен открытому); dispatch читает и подписывает — существующие HMAC-тесты (`test_webhooks_dispatch::test_webhook_signature_is_valid`) остаются зелёными (decrypt возвращает исходный секрет); ротация перешифровывает; легаси-открытый секрет в БД → dispatch подписывает им же.

**Гейты:** backend-регресс (webhooks/notifications/outbox + новый) одним прогоном; `ruff --no-fix`+format; **OpenAPI snapshot** (схемы ответа не меняются — секрет всё так же отдаётся при создании; сверить EXIT 0); полный SQLite-suite; docs (матрица SEC-67, CHANGELOG, handoff).

## 8. Риски / грабли

- **Тесты, читающие `row.secret` как открытый текст** — после врезки там шифротекст; такие ассерты чинить на `decrypt_secret(...)` или на API-ответ (он отдаёт открытый). Прогнать webhook-тесты первыми.
- **Ключ в prod обязателен** — иначе encrypt кидает (fail-closed). Документировать env `APP_SECRET_ENCRYPTION_KEY`.
- **Совместимость чтения** — decrypt обязан passthrough-ить открытый легаси (иначе старые вебхуки сломают подпись). Покрыто тестом.
- **Стабильность dev-ключа** — производный от `SECRET_KEY`; если `SECRET_KEY` меняется между записью и чтением в dev, расшифровка легаси-enc сломается. В тестах `SECRET_KEY` стабилен в рамках процесса — ок.
- **GCM nonce уникальность** — `os.urandom(12)` на каждое шифрование.

## 9. Порядок реализации

1. `core/secret_cipher.py` + settings-ключ.
2. Unit-тесты крипто.
3. Врезка encrypt-on-write (`api/routes/webhooks.py`) + decrypt-on-read (`services/webhooks.py`).
4. API/service-тесты + прогон webhook-регресса.
5. Гейты: ruff, openapi, полный suite; docs.
