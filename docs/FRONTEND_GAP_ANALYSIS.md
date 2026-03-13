# FRONTEND_GAP_ANALYSIS

## 1. Выявленные недочёты в текущем проходе

### UX/flow gaps
- В `PackWizard` не хватало явного восстановимого error state на submit.
- После успешного запуска мастер не сбрасывал контекст создания (company/preset/params), что ухудшало повторный запуск.
- Disabled CTA в мастере не объясняли причину блокировки.

### Upload UX gaps
- `FileUploader` имел упрощённый статус `Загрузка...` без прозрачного жизненного цикла файлов.
- Не было явной обработки частичных ошибок при пакетной загрузке.
- Валидация формата/размера не была выражена через `dropzone`-ограничения и сообщения.

### Permission/route confidence gaps
- Требовалась явная регрессия по изоляции client portal и admin-only зон на уровне guard-тестов.

## 2. Что исправлено

1. **PackWizard hardening**
   - Добавлены submit error + toast и восстановимый сценарий после сбоя.
   - Введён reset мастера после успешного сценария «Создать ещё один пакет».
   - Добавлены explainable disabled states (`title`) для основных CTA.

2. **FileUploader hardening**
   - Введены этапные статусы на файл: `pending/uploading/processing/ready/error`.
   - Добавлен список загрузок с прогресс-баром и текстовыми ошибками.
   - Добавлены ограничения `accept` + `maxSize`, обработка `onDropRejected`.
   - Добавлены UX-ветки: полный успех / частичный успех / полный fail.

3. **Тестовая стабилизация обязательных frontend зон**
   - Добавлены тесты для wizard navigation+validation+error recovery.
   - Добавлены тесты upload error states.
   - Добавлен тест route permission matrix для client/admin изоляции.
   - Расширена tenant-aware проверка request preparation при tenant switch.

## 3. Какие gaps закрыты

- Package wizard: закрыты дыры по validation/error/retry UX.
- Upload flows: закрыты silent-failure и слабая прозрачность статусов.
- Permission UX: усилена проверяемость route guards для критичных зон доступа.
- Tenant UX: подтверждён корректный заголовок tenant после runtime switch.

## 4. Доведённые секции

- Генерация (wizard).
- Файлы (загрузка / обработка / ошибки).
- Базовый permission слой (client portal/admin routes).
- Tenant-aware запросы на уровне API клиента.

## 5. Оставшиеся ограничения (только backend-dependent)

- Детализация некоторых ошибок на доменных endpoint-ах.
- Точный byte-level upload progress без серверного канала прогресса.
- Полный multi-tenant browser E2E в CI без стабильного backend testbed.


## 6. Дополнение текущего прохода
- Добавлен явный `role="alert"` для ошибок submit в `PackWizard`, чтобы ошибка не терялась и была доступна для assistive UX.
- Для финального шага мастера добавлен `aria-live` и выделенный success-блок для устойчивой обратной связи.
- В `FileUploader` добавлена статусная семантика (`В очереди/Загрузка/Проверка/Готово/Ошибка`) и `aria-live` для прогресса строк загрузки.
- Добавлены test hooks для ускорения polling в unit-тестах (`pollAttempts/pollIntervalMs`), чтобы убрать нестабильность по таймаутам.

## 7. Дополнительно закрыто в этом проходе
- Устранён дефект проверки прогресса в `FileUploader` тестах: отображение прогресса теперь валидируется по фактическому UI-паттерну статуса строки (`Готово · 100%`), без хрупкой привязки к отдельному текстовому узлу.
- Добавлен hardening drag&drop зоны: во время активной загрузки зона переводится в disabled-состояние (`disabled` в dropzone + `aria-disabled`), чтобы исключить race-condition с повторным drop.
