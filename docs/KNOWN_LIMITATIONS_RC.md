# Known Limitations (RC)

## Внешние зависимости
1. `/readyz` зависит от доступности Postgres и Redis; без них endpoint возвращает `503` (ожидаемое поведение для production-readiness).
2. Полные smoke-сценарии миграций/очередей/файлов требуют поднятого инфраструктурного контура (docker compose или эквивалент).

## Backend
1. Локальная проверка backend в этом проходе была выполнена в режиме compile/import + contract sanity; полный долгий прогон всего backend test-suite требует отдельного окна времени и инфраструктурных сервисов.
2. При локальном запуске без настроенного production-ключа используется development JWT key-pair (лог-предупреждение, не для prod).

## Frontend
1. `npm run ci` проходит, но тестовый лог содержит множество React `act(...)` warnings.
2. `vite build` предупреждает о крупных чанках (>500kB), требуется последующая оптимизация code-splitting.

## DevOps / e2e
1. Для финального sign-off требуется обязательный end-to-end smoke в среде, близкой к production, с поднятыми зависимостями и tenant-проверками.
