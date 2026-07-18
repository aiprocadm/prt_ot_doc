# Security Remediation Progress (2026-04-07)

Этот документ фиксирует фактический прогресс по блоку рисков R1-R10 из аудита и служит быстрым статусом для команды.

## Закрыто

- **R1 (Секреты в шаблонах)**  
  Обновлены `.env.example` и `backend/.env.example`: удалены небезопасные дефолты, добавлены явные предупреждения.

- **R2 (JWT конфигурация)**  
  В `backend/app/core/config.py` ужесточена проверка: для `staging/production` ключи обязательны, dev keypair запрещен.  
  Добавлены тесты в `tests/test_settings_staging_hardening.py`.

- **R3 (401/refresh loop во фронтенде)**  
  В `frontend/src/api/client.ts` добавлен ранний `Promise.reject(error)` при отсутствии access token и корректный выход при неуспешном refresh.  
  Добавлен unit-тест в `frontend/src/__tests__/apiClient.test.ts`.

- **R4 (search_path leakage)**  
  В `backend/app/db/session.py` добавлен сброс `search_path` при выходе из `get_tenant_session`.  
  Добавлен тест контракта сессии в `tests/test_tenant_session_contract.py`.

- **R5 (streaming upload)**  
  В `backend/app/api/routes/files.py` загрузка переведена на потоковую обработку через временный файл, без накопления полного payload в RAM.  
  В `backend/app/domains/files/s3.py` `put_object` поддерживает поток (`BinaryIO`) и `bytes`.  
  Добавлен тест в `tests/test_files_upload.py`.

- **R6 (ClamAV pending/download gate)**  
  Подтверждено тестом, что скачивание блокируется, пока файл не прошел сканирование (`pending/quarantine`).  
  Тест: `tests/test_files_upload.py::test_download_blocks_file_while_scan_pending`.

- **R7 (контракт ошибок + correlation_id)**  
  Базовый единый контракт уже реализован в `backend/app/api/error_handlers.py`, дополнительно унифицированы ошибки для `companies` через `api_problem_detail`.  
  Добавлены проверки в `tests/api/test_company_crud.py`.

- **R8 (IDOR/cross-tenant tests)**  
  Расширено integration покрытие в `tests/integration/test_cross_tenant_resource_matrix.py` для ресурсов:
  - files records
  - outbox
  - documents batch
  - templates versions
  - sites
  - documents
  - tasks status
  - workflow instances

  Также устранен реальный leak в `GET /api/v1/tasks/{task_id}`: теперь ранний `404`, если tenant-bound `PipelineRun` не найден.

- **R10 (Nginx quick hardening)**  
  В `proxy/nginx.conf` добавлены `SameSite`/`Secure` для cookies и базовый `limit_req` для `/api/`.

## Частично закрыто / осталось

- **R7 (глубокая унификация ошибок во всех модулях)**  
  Контракт есть, но часть legacy-роутов еще использует разнородные сообщения/коды.  
  Нужна доводка по remaining high-traffic endpoints.

- **R8 (ширина покрытия)**  
  Критичные IDOR-пути расширены, но требуется дальнейшее покрытие по workflow/risk/obligations и отказоустойчивости внешних зависимостей.

- **R9 (cache/perf)**  
  Не начато в рамках этого пакета.

## Рекомендованный следующий пакет

1. Добить remaining high-risk интеграционные сценарии (workflow/risk/tasks edge-cases).
2. Добавить CI gate на default-secrets (fail pipeline при небезопасных значениях).
3. Сделать короткий security regression suite job (быстрый nightly прогон).
