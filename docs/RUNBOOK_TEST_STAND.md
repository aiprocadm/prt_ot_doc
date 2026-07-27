# Runbook — тестовый стенд doc.ptsfera.online

**Owner**: ops / тех.лид
**Scope**: как устроен демо-стенд, как он сам обновляется до `main`, как поднять его с нуля и что проверять, когда «сайт не открывается».
**Контекст**: стенд нужен, чтобы смотреть результат разработки в браузере глазами пользователя и показывать его заказчику. Поэтому он не заморожен на релизе, а догоняет `main` автоматически. Это **не production**: база — SQLite, хранилище локальное, данные тестовые.

---

## 1. Устройство

| Часть | Где | Комментарий |
|---|---|---|
| Код стенда | `/home/aiproc/stands/prt_ot_doc` | **Отдельная копия** репозитория: своё окружение Python, свои `node_modules`, свой `.env.production` (chmod 600, в git НЕ хранится) |
| Код разработки | `/home/aiproc/projects/prt_ot_doc` | Отдан сессиям разработки целиком, стенда не касается |
| Витрина | статика `frontend/dist` внутри копии, отдаёт nginx | Пересобирается при каждом обновлении |
| Двигатель | служба `ptd-doc-web` → `127.0.0.1:8000` | uvicorn `app.main:app`, `User=aiproc`, `Restart=always` |
| База | SQLite `dev.db` **внутри копии** | Своя, отдельная от разработки. Путь задан абсолютным `DATABASE_URL` |
| Адрес | `doc.ptsfera.online` | basic-auth, логин `demo`, файл `/etc/nginx/.htpasswd-stand` |
| Вход в приложение | `admin@example.com` / `admin123`, тенант `demo` | Без заголовка `X-Tenant` любой роут отдаёт 400 `TENANT_REQUIRED` |
| Обновление | cron `*/10 * * * *` → `infra/stand/update-stand.sh` | Полный цикл ≈ 35 секунд |

Образцы файлов: [`infra/stand/`](../infra/stand/) — скрипт обновления, юнит systemd, конфиг nginx.

**Один поддомен на проект:** витрина в корне, двигатель под `/api` того же домена. Отдельного API-поддомена нет намеренно — иначе понадобился бы CORS. Схема заработала без правок фронтенда, потому что `frontend/src/config/env.ts` по умолчанию использует относительный `apiBaseUrl = "/api/v1"`.

### Почему копия отдельная

Стенд и разработка спорят за одни и те же артефакты сборки. Отладочный запуск, смена ветки или переустановка зависимостей соседней сессией оставляют стенд без собранной витрины, и служба уходит в бесконечный цикл падений. **Это не теория: на этом сервере такое уже приводило к простою в несколько суток**, причём внешне выглядело сетевой проблемой и увело диагностику совсем не туда. Разделение папок закрывает причину, а не симптом.

По той же причине у копии **своя база**: `make cs:reset` или пересоздание `dev.db` в папке разработки стенда больше не касается.

---

## 2. Как обновляется

`infra/stand/update-stand.sh` (cron, каждые 10 минут, от пользователя `aiproc`, **без sudo**):

1. `git fetch` → нет нового коммита в `origin/main` → **молча выходит**.
2. Есть новый → снимок `frontend/dist` как страховка.
3. `git reset --hard` → зависимости Python **только если** сменился `requirements.txt` → зависимости фронтенда **только если** сменился `frontend/package-lock.json` → сборка витрины.
4. Успех → `kill` главного процесса службы; systemd поднимет её с новым кодом.
5. **Любая осечка → откат**: код возвращается на прежний коммит, витрина восстанавливается из снимка, служба не трогается, причина пишется в журнал.

Решения, которые легко случайно «оптимизировать»:

- **Перезапуск через `kill`, а не `systemctl restart`.** Служба объявлена с `User=aiproc`, поэтому сигнал своему же процессу проходит без прав root, а `Restart=always` возвращает её через 5 секунд. Весь цикл обходится без sudo.
- **Скрипт переезжает на временную копию себя** и только потом делает `git reset --hard`. Он лежит внутри той же копии, которую перезаписывает, а bash дочитывает файл по ходу выполнения — подмена на середине привела бы к непредсказуемому поведению.
- **Alembic не гоняется.** Схему SQLite приложение создаёт само при старте (`prepare_runtime` → `create_all`). Новые таблицы подхватываются автоматически.

### Команды на каждый день

```bash
tail -20 /home/aiproc/stands/logs/doc-update.log            # что и когда обновлялось
/home/aiproc/stands/prt_ot_doc/infra/stand/update-stand.sh  # обновить сейчас, не ждать
```

Ручной запуск безопасен: если нового кода нет, скрипт ничего не делает.

`ПРЕДУПРЕЖДЕНИЕ: не нашёл процесс службы` в журнале — безобидно. Служба в этот момент была в паузе перезапуска и стартовала уже с новым кодом.

### Если после обновления посыпались ошибки про отсутствующую колонку

`create_all` добавляет новые **таблицы**, но не меняет колонки в существующих. Значит базе стенда нужна свежая:

```bash
kill $(systemctl show -p MainPID --value ptd-doc-web)   # служба уйдёт в перезапуск
rm /home/aiproc/stands/prt_ot_doc/dev.db                # успеть между попытками
```

Схема создастся заново при старте, демо-данные засеются (`DEMO_BOOTSTRAP`). Данные стенда тестовые, терять нечего.

---

## 3. Развернуть с нуля

```bash
# 1. Отдельная копия кода
mkdir -p /home/aiproc/stands
git clone --depth=1 --branch main https://github.com/aiprocadm/prt_ot_doc.git \
          /home/aiproc/stands/prt_ot_doc
cd /home/aiproc/stands/prt_ot_doc

# 2. Настройки (из менеджера секретов владельца; в git их нет)
cp /путь/к/.env.production .  &&  chmod 600 .env.production
# ОБЯЗАТЕЛЬНО абсолютные пути — служба работает не из папки разработки:
#   DATABASE_URL=sqlite+aiosqlite:////home/aiproc/stands/prt_ot_doc/dev.db
#   STORAGE_ROOT=/home/aiproc/stands/prt_ot_doc/.local_storage

# 3. Окружение Python
#    Системный `python -m venv` на этом сервере БЕЗ ensurepip (нет пакета
#    python3.12-venv, а sudo недоступен) — окружение создаётся через uv.
/home/aiproc/.local/bin/uv venv .venv --python 3.12
/home/aiproc/.local/bin/uv pip install -r requirements.txt --python .venv/bin/python

# 4. Витрина
export PATH=/home/aiproc/.nvm/versions/node/v24.18.0/bin:$PATH
(cd frontend && npm ci && npm run build)

# 5. Двигатель
sudo cp infra/stand/ptd-doc-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ptd-doc-web

# 6. Публикация
sudo chmod o+x /home/aiproc          # чтобы nginx (www-data) дошёл до frontend/dist
sudo cp infra/stand/nginx/doc.ptsfera.online.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/doc.ptsfera.online.conf /etc/nginx/sites-enabled/
sudo htpasswd /etc/nginx/.htpasswd-stand demo     # пароль — из менеджера секретов
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d doc.ptsfera.online

# 7. Автообновление
crontab -l 2>/dev/null | { cat; \
  echo '*/10 * * * * /home/aiproc/stands/prt_ot_doc/infra/stand/update-stand.sh'; } | crontab -
```

**После certbot** конфиг nginx нельзя перезаписывать целиком — только точечно (`sudo sed -i ...`), иначе дописанные им блоки 443 пропадут и HTTPS отвалится.

---

## 4. Грабли, на которые уже наступали

| Симптом | Причина | Лечение |
|---|---|---|
| **После входа в приложение снова требует пароль nginx, войти невозможно** | Приложение кладёт токен в заголовок `Authorization`, а браузер держит там же пропуск basic-auth — карман один, токен вытесняет пропуск | `auth_basic off;` внутри `location /api/` (уже в конфиге). Правку в живой конфиг вносить точечно, шаблон поверх не копировать |
| **Белый экран, в консоли `Cannot read properties of undefined (reading 'useState')`** | Разбивка vendor-чанков по подстроке пути ловила `react-hook-form`, `react-i18next`, `lucide-react`, `@radix-ui/react-*` в чанк react → встречные зависимости, React становился undefined. В dev-режиме не видно: там модули не склеиваются | Исправлено в `frontend/vite.config.ts` (PR #765): все зависимости одним чанком |
| **Служба не стартует: `Missing required environment variables: S3_ACCESS_KEY, S3_SECRET_KEY`** | В `.env` они **пустые** и перекрывают дефолты; `scripts/dev_lite.py` подставлял их на лету, systemd — нет | Задать любые непустые в `.env.production` (хранилище всё равно `STORAGE_BACKEND=local`) |
| **Служба не стартует: приложение ломится в Postgres** | В копии стенда нет dev-файла `.env`, откуда бралось `DATABASE_URL`; по умолчанию конфиг собирает адрес Postgres | Задать `DATABASE_URL` явно в `.env.production`, абсолютным путём |
| **Запросы отвергаются TrustedHostMiddleware** | `APP_TRUSTED_HOSTS` не включает поддомен | Добавить `doc.ptsfera.online` |
| **Требует пару RSA-ключей, пароль Postgres и прочее** | `APP_ENV=production/staging` тянет полный боевой набор | Для стенда оставить `APP_ENV=development` + `APP_DEBUG=false` + `ENABLE_OPENAPI_DOCS=false` |
| **Не открывается в Chrome/Яндексе, хотя `curl` даёт честный 401** | Кириллица в `auth_basic` — по RFC там только ASCII, браузер молча не показывает окно пароля | Realm только латиницей. Проверка: `curl -D - -H "Host: <домен>" -k https://127.0.0.1/ \| grep -i www-authenticate` |
| **nginx отдаёт 403 на витрину** | Домашний каталог `drwxr-x---`, www-data не доходит до `frontend/dist`. Пакета acl на сервере нет, `setfacl` недоступен | `sudo chmod o+x /home/aiproc` — право прохода без листинга |

---

## 5. «Сайт не открывается» — порядок диагностики

Проверять **снизу вверх**: сначала свой процесс, потом сеть. Обратный порядок однажды стоил суток разбирательства, а причина была на сервере.

```bash
ss -lnt | grep :8000                       # 1. слушает ли порт
systemctl status ptd-doc-web               # 2. строку Active: читать ЦЕЛИКОМ
journalctl -u ptd-doc-web -n 50            # 3. что пишет при падении
curl -s -o /dev/null -w '%{http_code}\n' -m 15 http://127.0.0.1:8000/   # 400 = жив (нужен X-Tenant)
```

- **`systemctl is-active` ВРЁТ**: в цикле перезапусков отвечает `active`, хотя служба на самом деле `activating (auto-restart)`. Смотреть только полный `systemctl status`.
- **Двигатель стартует ~20 секунд.** Сразу после перезапуска `код=000` — это норма, а не поломка.
- **Быстрый разделитель «сервер или сеть»:** на сервере опубликовано несколько стендов, каждый своим процессом на своём порту. Если часть поддоменов открывается, а часть нет — виноват процесс: сетевая поломка положила бы все сразу.
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

---

## 6. Что стенд НЕ показывает

- **Только влитую `main`.** Незалитая ветка на стенде не появится — под это нужен отдельный адрес и отдельная копия.
- **Задержка до ~11 минут** между мержем в `main` и появлением на стенде (10 минут расписания + ~35 секунд сборки). Кому надо сразу — ручной запуск скрипта.
- **Сломанный код в `main` стенд не уронит**, но и не покажет: он останется на прошлой рабочей версии, а причина будет в журнале обновлений.
