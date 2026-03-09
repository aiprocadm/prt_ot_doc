# FINAL_CRITICAL_GAPS

1. **ORM relationship overlaps warnings (risk domain)**  
   - Почему важно: повышает риск скрытых ошибок маппинга и деградации сопровождения.  
   - Следующий шаг: поправить `overlaps/back_populates` в моделях risk/workplace/position и закрепить тестом без warning-as-error.

2. **Backup/restore не формализован как обязательный периодический drill**  
   - Почему важно: критично для B2B SaaS SLA и инцидент-готовности.  
   - Следующий шаг: добавить автоматический сценарий восстановления tenant snapshot + smoke-тест после restore.

3. **Неполная e2e матрица ролей на frontend**  
   - Почему важно: риск утечки видимости/действий в клиентском интерфейсе.  
   - Следующий шаг: добавить Playwright/Vitest e2e на ключевые restricted routes и action buttons.

4. **Enterprise-hardening файлового контура**  
   - Почему важно: для прома требуется строгая AV/DLP/governance политика и аудит скачиваний/подписанных URL.
   - Следующий шаг: централизовать policy checks и включить их в обязательный release-gate.
