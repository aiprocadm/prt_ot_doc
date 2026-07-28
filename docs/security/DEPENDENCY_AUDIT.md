# SEC-64 (разд. 64.1): аудит зависимостей — состояние и план ужесточения

ТЗ требует «Vulnerable Components: **Trivy + pip-audit + npm audit** в CI (Trivy уже
есть)». Оба недостающих инструмента добавлены в `ci.yml`, но **в observe-mode**
(`continue-on-error: true`) — и это осознанное решение, а не недоделка.

## Почему observe-mode, а не блокирующий гейт

На момент включения инструменты дают:

| Инструмент | Находок | Основные пакеты |
|---|---|---|
| `pip-audit` | **18** | `starlette 0.41.3`, `python-multipart 0.0.27`, `ecdsa 0.19.2`, `pytest 8.3.3`, `python-dotenv 1.0.1` |
| `npm audit --audit-level=high` | **31** (21 high, 2 critical) | транзитивные, включая `ws` |

Сделать их блокирующими сразу — значит покрасить CI на **всех** PR, включая те, что к
зависимостям отношения не имеют. Разработка встанет, а гейт отключат — ровно тот
исход, ради предотвращения которого он и вводится. В репозитории уже есть прецедент
такого поэтапного ввода: semgrep работает в observe-mode (разд. 69).

Ценность observe-mode не нулевая: отчёт печатается в summary каждого прогона, поэтому
**новая** уязвимость видна сразу, а не всплывает на аудите перед релизом.

## Что мешает закрыть долг прямо сейчас

Главный блокер — `starlette`: путь от `0.41.3` к версиям без advisories ведёт через
мажорные `1.x`, а это ломающие изменения в слое middleware (проект держит собственные
`SecurityHeadersMiddleware`, `TenantMiddleware`, `ObservabilityMiddleware`, а также
зависит от `fastapi`, который тянет свой диапазон starlette). Такой апгрейд — отдельная
задача с прогоном всего набора, а не строчка в security-PR.

`python-multipart` и `python-dotenv` поднимаются малой кровью; `pytest` и `ecdsa` —
dev/транзитивные.

## Порядок перевода в блокирующие

1. Поднять то, что обновляется без ломающих изменений (`python-multipart`,
   `python-dotenv`), и убедиться, что счётчик находок падает.
2. Отдельной задачей — `fastapi`/`starlette` до версий без advisories, с полным
   прогоном набора и db-гейта.
3. Для остатка, который осознанно не обновляется, — записи в
   `.github/security-exceptions.yml` с обоснованием и сроком пересмотра (механизм уже
   используется для Trivy: `scripts/ci/render_trivyignore.py`).
4. Убрать `continue-on-error` сначала у `pip-audit`, затем у `npm audit`.

Пункт 3 обязателен: без него шаг 4 просто вернёт красный CI.

## Как проверить локально

```bash
python -m pip install pip-audit
pip-audit --requirement requirements.txt --requirement requirements-dev.txt
npm --prefix frontend audit --audit-level=high
```

`pip-audit` создаёт временное окружение; на Debian/Ubuntu без пакета `python3-venv`
он падает — тогда запускайте `pip-audit` без `--requirement` (аудит уже установленного
окружения).
