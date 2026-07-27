# Runbook — тестовый стенд doc.ptsfera.online

**Owner**: ops / тех.лид
**Scope**: как устроен демо-стенд prt_ot_doc, как его поднять с нуля, как обновлять и что проверять, когда «сайт не открывается».
**Контекст**: стенд нужен для показа и для проверки результата глазами пользователя. Это **не production**: БД — SQLite `dev.db`, хранилище локальное, данные тестовые.

---

## 1. Устройство

| Часть | Где | Комментарий |
|---|---|---|
| Витрина | статика `frontend/dist`, отдаёт nginx напрямую | Пересобирать после каждого изменения фронтенда |
| Двигатель | служба `ptd-doc-web` → `127.0.0.1:8000` | uvicorn `app.main:app`, `User=aiproc`, `Restart=always` |
| Адрес | `doc.ptsfera.online` | basic-auth, логин `demo`, файл `/etc/nginx/.htpasswd-stand` |
| Вход в приложение | `admin@example.com` / `admin123`, тенант `demo` | Без заголовка `X-Tenant` любой роут отдаёт 400 `TENANT_REQUIRED` |

Образцы файлов: [`infra/stand/`](../infra/stand/) — юнит systemd, конфиг nginx, скрипт пересборки.

**Один поддомен на проект:** витрина в корне, двигатель под `/api` того же домена. Отдельного API-поддомена нет намеренно — иначе понадобился бы CORS. Схема заработала без правок фронтенда, потому что `frontend/src/config/env.ts` по умолчанию использует относительный `apiBaseUrl = "/api/v1"`.

---

## 2. Обновление стенда

```bash
infra/stand/rebuild-stand.sh              # пересобрать витрину + перезапустить двигатель
STAND_SKIP_BUILD=1 infra/stand/rebuild-stand.sh   # только перезапустить двигатель
```

Скрипт **не трогает git** — ни fetch, ни checkout, ни reset. Это сознательное ограничение: стенд пока живёт в общей папке с разработкой, и любая операция с git снесла бы чужую незакоммиченную работу. Собирается ровно тот код, что сейчас в рабочей папке.

Если сборка витрины падает, скрипт возвращает предыдущую рабочую `dist` и не трогает службу.

**Известный риск.** Стенд и разработка делят одну папку. Отладочный запуск или смена ветки соседней сессией может оставить стенд без собранной витрины, и служба уйдёт в бесконечный цикл падений. Это не теория: на этом сервере такое уже приводило к простою стенда длиной в несколько суток, причём внешне выглядело как сетевая проблема. Радикальное лечение — отдельная копия репозитория под стенд, чтобы разработка физически не могла его задеть; здесь оно ещё не сделано.

---

## 3. Развернуть с нуля

```bash
cd /home/aiproc/projects/prt_ot_doc

# 1. Настройки (из менеджера секретов; в git их нет)
cp /путь/к/.env.production .  &&  chmod 600 .env.production

# 2. Витрина
cd frontend && npm ci && npm run build && cd ..

# 3. Двигатель
sudo cp infra/stand/ptd-doc-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ptd-doc-web

# 4. Публикация
sudo chmod o+x /home/aiproc          # чтобы nginx (www-data) дошёл до frontend/dist
sudo cp infra/stand/nginx/doc.ptsfera.online.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/doc.ptsfera.online.conf /etc/nginx/sites-enabled/
sudo htpasswd /etc/nginx/.htpasswd-stand demo     # пароль — из менеджера секретов
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d doc.ptsfera.online
```

**После certbot** конфиг nginx нельзя перезаписывать целиком — только точечно (`sudo sed -i ...`), иначе дописанные им блоки 443 пропадут и HTTPS отвалится.

---

## 4. Грабли, на которые уже наступали

| Симптом | Причина | Лечение |
|---|---|---|
| **После входа в приложение снова требует пароль nginx, войти невозможно** | Приложение кладёт токен в заголовок `Authorization`, а браузер держит там же пропуск basic-auth — карман один, токен вытесняет пропуск | `auth_basic off;` внутри `location /api/` (уже в конфиге). Правку в живой конфиг вносить точечно, шаблон поверх не копировать |
| **Белый экран, в консоли `Cannot read properties of undefined (reading 'useState')`** | Разбивка vendor-чанков по подстроке пути ловила `react-hook-form`, `react-i18next`, `lucide-react`, `@radix-ui/react-*` в чанк react → встречные зависимости, React становился undefined. В dev-режиме не видно: там модули не склеиваются | Исправлено в `frontend/vite.config.ts` (PR #765): все зависимости одним чанком |
| **Служба не стартует: `Missing required environment variables: S3_ACCESS_KEY, S3_SECRET_KEY`** | В `.env` они **пустые** и перекрывают дефолты; `scripts/dev_lite.py` подставлял их на лету, systemd — нет | Задать любые непустые в `.env.production` (хранилище всё равно `STORAGE_BACKEND=local`) |
| **Запросы отвергаются TrustedHostMiddleware** | `APP_TRUSTED_HOSTS` не включает поддомен | Добавить `doc.ptsfera.online` |
| **Требует пару RSA-ключей, пароль Postgres и прочее** | `APP_ENV=production/staging` тянет полный боевой набор | Для стенда оставить `APP_ENV=development` + `APP_DEBUG=false` + `ENABLE_OPENAPI_DOCS=false` |
| **Не открывается в Chrome/Яндексе, хотя `curl` даёт честный 401** | Кириллица в `auth_basic` — по RFC там только ASCII, браузер молча не показывает окно пароля | Realm только латиницей. Проверка: `curl -D - -H "Host: <домен>" -k https://127.0.0.1/ \| grep -i www-authenticate` |
| **nginx отдаёт 403 на витрину** | Домашний каталог `drwxr-x---`, www-data не доходит до `frontend/dist`. Пакета acl на сервере нет, `setfacl` недоступен | `sudo chmod o+x /home/aiproc` — право прохода без листинга |

---

## 5. «Сайт не открывается» — порядок диагностики

Проверять **снизу вверх**: сначала свой процесс, потом сеть. Обратный порядок однажды стоил суток разбирательства при поломке на сервере.

```bash
ss -lnt | grep :8000                       # 1. слушает ли порт
systemctl status ptd-doc-web               # 2. строку Active: читать ЦЕЛИКОМ
journalctl -u ptd-doc-web -n 50            # 3. что пишет при падении
curl -s -o /dev/null -w '%{http_code}\n' -m 15 http://127.0.0.1:8000/   # 400 = жив (нужен X-Tenant)
```

- **`systemctl is-active` ВРЁТ**: в цикле перезапусков отвечает `active`, хотя служба на самом деле `activating (auto-restart)`. Смотреть только полный `systemctl status`.
- **Двигатель стартует ~20 секунд.** Сразу после перезапуска `код=000` — это норма, а не поломка.
- **Быстрый разделитель «сервер или сеть»:** если часть поддоменов работает, а часть нет — виноват процесс, а не сеть.
- **Hairpin NAT не работает:** запрос с сервера на свой же внешний адрес даёт `код=000`. Это НЕ признак закрытого порта.
- **На сервере поднят локальный прокси** — всегда `curl --noproxy '*'`, иначе коды будут мусорные.

**Внешняя проверка** (WebFetch к этим доменам стабильно врёт «Socket is closed»):

```bash
curl --noproxy '*' -H "Accept: application/json" \
  "https://check-host.net/check-http?host=https%3A%2F%2Fdoc.ptsfera.online&max_nodes=4"
curl --noproxy '*' -H "Accept: application/json" \
  "https://check-host.net/check-result/<request_id>"
```

`401` от чужих машин = стенд работает и защищён паролем.
