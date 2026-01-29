# Tenant isolation report (phase 3)

## Scope

Проверка multi-tenant изоляции данных и событий между двумя арендаторами с одинаковой структурой данных.

## Test assets

- Скрипт: `scripts/pilot/tenant_isolation.sh`.
- Тестовые арендаторы: `pilot-a`, `pilot-b`.

## Findings

| Проверка | Результат | Комментарий |
| --- | --- | --- |
| Нет cross-tenant чтения | ⬜️ | Заполнить после прогона скрипта. |
| Нет cross-tenant событий/webhooks | ⬜️ | Проверить outbox по tenant_id. |
| Нет смешения метрик | ⬜️ | Проверить метрики с фильтром по tenant. |
| Ошибка выбора неверного tenant | ⬜️ | Проверить 403/404 при неверном `X-Tenant`. |

## Evidence

- Логи запросов/ответов.
- Выводы `/api/v1/admin/outbox` по каждому tenant.
- Метрики `outbox_*` с фильтром по tenant.

## Conclusion

_Заполнить после выполнения скрипта и фиксации результатов._
