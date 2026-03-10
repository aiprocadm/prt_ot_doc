# FINAL_CRITICAL_GAPS

1. **Неполный cleanup ORM relationship warnings (risk domain)**
   - Почему важно: предупреждения скрывают реальные конфликты записи в связях и усложняют сопровождение.
   - Следующий шаг: завершить `overlaps/back_populates` конфигурацию и включить warning-gate в critical checks.

2. **Недостаточная формализация backup/restore готовности**
   - Почему важно: без регулярного проверяемого восстановления нельзя гарантировать SLA/BCP.
   - Следующий шаг: автоматизировать restore tenant snapshot + smoke-проверку в CI/cron.

3. **Неполная e2e матрица доступа в UI**
   - Почему важно: риск утечки видимости/действий для ролей клиентского портала и админки.
   - Следующий шаг: добавить Playwright/Vitest e2e для restricted routes и критичных action-кнопок.

4. **Файловый контур не доведен до enterprise требований**
   - Почему важно: для прод-эксплуатации требуются централизованные политики AV/DLP и полный аудит скачиваний/подписанных ссылок.
   - Следующий шаг: централизовать policy checks и сделать их обязательной частью release gate.

   > Обновление: базовый guardrail по времени жизни presigned download URL уже введен (TTL ограничен в пределах 60..3600 секунд), но этого недостаточно для полного enterprise hardening.

- Закрыто в этой итерации: критичный разрыв tenant-контекста для inbound webhook задач (Celery tenant slug mismatch).

- Закрыто в этой итерации (дополнительно): критичный public-prefix bypass в tenant middleware (`/api/v1/publicity`) устранен и покрыт тестами.
- Закрыто в этой итерации: bypass tenant middleware по non-docs URL с суффиксом `openapi.json`.
