# Мастер пакета документов (Documents Wizard)

Страница: `/documents/wizard`.

## Поток F2/F3 (10 шагов)

1. Выбор пресета/проекта (manual fallback).
2. Загрузка CSV/XLSX с базовой валидацией размера и типа.
3. Маппинг колонок файла в поля шаблона.
4. Выбор `template_code` + `template_version`.
5. Настройки колонтитулов/макета.
6. Replace: загрузка карты замен CSV, dry-run, diff preview.
7. Запуск pipeline/batch с `Idempotency-Key`.
8. QA: фильтрация строк по статусам `success/failed`, построчные ошибки.
9. Экспорт артефактов ZIP/PDF.
10. Переход в архив + placeholder под ЭДО статусы.

## API интеграция

### Документы
- `POST /documents/generate` — single pipeline.
- `GET /documents/tasks/{task_id}` — статусы задачи.
- `POST /documents/batch` — запуск батча по строкам файла.
- `GET /documents/batch/{batch_id}` — агрегированный/построчный статус батча.

### Replace
- `POST /replace/dry-run` — dry-run replace и preview отчёт.
- `GET /replace/reports/{report_id}` — полный diff-отчёт.

### Pipeline
- `GET /v1/jobs/{job_id}` — timeline шагов pipeline (`queued/running/success/failed/...`) и artifacts.

### Files
- `GET /v1/files/{file_id}/download` — presigned download URL.

## Заголовки

Для всех бизнес API обязателен `X-Tenant`. На фронте это обеспечивается глобальным `apiClient` interceptor; если tenant не выбран, wizard блокирует запуск API действий на UI уровне.

`Idempotency-Key` генерируется и хранится в состоянии шага запуска (step 7).

## Хранение состояния

Состояние мастера хранится:
- в URL query (`?step=N`) для навигации/refresh,
- в persisted Zustand store (`documents-wizard-v1`) для восстановления введённых данных между перезагрузками.
