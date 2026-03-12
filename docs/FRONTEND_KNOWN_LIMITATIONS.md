# FRONTEND_KNOWN_LIMITATIONS

Ниже только реальные ограничения, которые остаются backend-dependent.

1. **Upload progress granularity**
   - Сейчас frontend показывает этапный прогресс (uploading/processing/ready/error).
   - Для точного серверного прогресса нужен backend канал прогресса (SSE/WebSocket/подробный polling contract).

2. **Domain-level structured API errors**
   - Для некоторых сценариев (редкие edge-cases в jobs/edo) сервер возвращает ограниченный `message` без унифицированного `details`.
   - Это снижает точность контекстных UX-подсказок при нештатных ошибках.

3. **Cross-tenant E2E on CI**
   - Unit/integration слой покрывает tenant-aware подготовку запросов.
   - Полный browser-level тест c переключением tenant и проверкой изоляции зависит от стабильного CI-стенда с подготовленными данными для нескольких контуров.
