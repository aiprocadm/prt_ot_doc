# KNOWN LIMITATIONS (RC)

Только реальные остаточные ограничения текущего кандидата.

## Backend
- Неполная стабилизация полного regression-сета `pytest -q`: остаются падения в ABAC/policy reason mapping, audit deny logging, pack download access control, replace API сценариях.
- Нужен дополнительный цикл выравнивания error-contract (`detail`/`reason`) между ABAC, error handlers и тестовыми ожиданиями.

## Frontend
- Критических блокеров сборки/типизации нет.
- В тестах есть шумные React warnings (`act(...)`), не блокирующие прохождение, но ухудшающие signal-to-noise CI логов.

## CI / DevEx
- Backend lint debt (ruff import/order/unused) остаётся значительным и не закрыт в рамках одного RC-прохода без масштабной реорганизации.

## Внешние интеграции
- PDF/office conversion зависит от наличия `soffice`; в текущей среде бинарь отсутствует, используется fallback/ограниченный сценарий.
