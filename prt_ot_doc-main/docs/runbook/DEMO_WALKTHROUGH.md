# DEMO WALKTHROUGH (MVP)

1. Скопируйте конфиг и включите bootstrap:
   - `cp .env.example .env`
   - в `.env` проверьте: `ADMIN_BOOTSTRAP=1`, `DEMO_BOOTSTRAP=1`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
2. Запустите локальный режим:
   - `make cs:dev`
3. Откройте UI, войдите под админом и выберите tenant `demo`.
4. Пройдите `/documents/wizard`:
   - preset,
   - данные (можно использовать `samples/data/people.csv`),
   - шаблон/версия,
   - запуск pipeline,
   - timeline шагов.
5. Проверьте outbox на `/admin/outbox`.
6. Проверьте доменные события через UI/API:
   - Risks (оценка риска),
   - PPE (выдача СИЗ),
   - Training (завершение обучения).
7. Запустите автотесты:
   - `make cs:test`
