# SEC-64 (разд. 64.1): аудит зависимостей — состояние и план ужесточения

ТЗ требует «Vulnerable Components: **Trivy + pip-audit + npm audit** в CI (Trivy уже
есть)». Состояние на 2026-07-30:

- **pip-audit — БЛОКИРУЮЩИЙ** (шаги 1, 3, 4 плана ниже выполнены): база находок
  вычищена подъёмом `python-multipart` 0.0.31 / `python-dotenv` 1.2.2 /
  `click` 8.3.3 (+`typer` 0.27.0 — typer<0.16 ломается на click>=8.2); осознанный
  остаток принят записями `tool: pip-audit` в `.github/security-exceptions.yml`
  (starlette ×7 — ждёт отдельного PR подъёма fastapi; ecdsa — апстрим-фикса нет;
  pytest 9 и black 26 — dev-only мажоры отдельными PR). Записи имеют срок
  `expires_on`, просрочку валит `check_security_exceptions.py`; в команду
  pip-audit они попадают как `--ignore-vuln` через
  `scripts/ci/render_pip_audit_ignores.py`. Новая advisory без записи = красный CI.
- **npm audit — всё ещё observe-mode** (`continue-on-error: true`) — осознанное
  решение, а не недоделка: 31 находка (21 high, 2 critical), в основном
  транзитивные. Перевод — следующий шаг, тем же механизмом.

## Почему изначально observe-mode, а не блокирующий гейт

На момент включения (до чистки 2026-07-30) инструменты давали:

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

1. ~~Поднять то, что обновляется без ломающих изменений~~ — **сделано 2026-07-30**:
   `python-multipart` 0.0.31, `python-dotenv` 1.2.2, `click` 8.3.3 + `typer` 0.27.0.
2. Отдельной задачей — `fastapi`/`starlette` до версий без advisories, с полным
   прогоном набора и db-гейта. Туда же (отдельными PR): `pytest` 9.x
   (тянет совместимость pytest-asyncio/cov/timeout/xdist) и `black` 26.x
   (меняет стиль — потребует переформатирования под `make lint`).
3. ~~Для остатка — записи в `.github/security-exceptions.yml`~~ — **сделано**:
   11 записей `tool: pip-audit` со сроками; в CLI попадают через
   `scripts/ci/render_pip_audit_ignores.py` (аналог `render_trivyignore.py`).
4. Убрать `continue-on-error`: у `pip-audit` — **сделано** (шаг «pip-audit gate»
   в `ci.yml`); у `npm audit` — осталось (нужна своя чистка/исключения, у npm
   audit нет штатного ignore-механизма).

## Как проверить локально

```bash
python -m pip install pip-audit
pip-audit --requirement requirements.txt --requirement requirements-dev.txt
npm --prefix frontend audit --audit-level=high
```

`pip-audit` создаёт временное окружение; на Debian/Ubuntu без пакета `python3-venv`
он падает — тогда запускайте `pip-audit` без `--requirement` (аудит уже установленного
окружения).
