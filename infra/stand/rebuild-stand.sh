#!/usr/bin/env bash
# Пересборка витрины тестового стенда doc.ptsfera.online и перезапуск двигателя.
# См. docs/RUNBOOK_TEST_STAND.md.
#
# Что делает: собирает frontend/dist из того кода, что СЕЙЧАС в рабочей папке,
# и перезапускает службу FastAPI. Git не трогает вообще — ни fetch, ни checkout,
# ни reset. Это сознательное ограничение: стенд doc пока живёт в общей папке
# с разработкой, и любая операция с git там снесла бы чужую незакоммиченную
# работу. Автоподтягивание main появится только после переезда стенда
# в отдельную копию (как это сделано в lk_otsfera).
#
# Витрину нужно пересобирать руками после каждого изменения фронтенда:
# nginx отдаёт именно папку dist, а не исходники.
#
# Зависимости: node/npm (путь задаётся STAND_NODE_BIN), systemd.
# sudo НЕ нужен: служба объявлена с User=aiproc, поэтому перезапуск делается
# сигналом своему же процессу, а Restart=always поднимет её обратно.
#
# Env:
#   STAND_DIR       — папка проекта (default /home/aiproc/projects/prt_ot_doc)
#   STAND_UNIT      — служба двигателя (default ptd-doc-web)
#   STAND_NODE_BIN  — папка с node/npm (default /home/aiproc/.nvm/versions/node/v24.18.0/bin)
#   STAND_SKIP_BUILD=1 — только перезапустить двигатель, витрину не трогать

# Намеренно без `set -e`: ошибки перехватываются по шагам, чтобы успеть
# вернуть предыдущую рабочую витрину.
set -uo pipefail

STAND_DIR="${STAND_DIR:-/home/aiproc/projects/prt_ot_doc}"
STAND_UNIT="${STAND_UNIT:-ptd-doc-web}"
STAND_NODE_BIN="${STAND_NODE_BIN:-/home/aiproc/.nvm/versions/node/v24.18.0/bin}"

export PATH="$STAND_NODE_BIN:$PATH"

say() { echo "[stand] $*"; }

cd "$STAND_DIR" || { say "ОШИБКА: нет папки $STAND_DIR"; exit 1; }

if [[ "${STAND_SKIP_BUILD:-}" != "1" ]]; then
    cd frontend || { say "ОШИБКА: нет папки frontend"; exit 1; }

    # Снимок рабочей витрины: если сборка упадёт, посетители не должны
    # увидеть пустую или наполовину обновлённую папку.
    rm -rf dist.bak
    [[ -d dist ]] && cp -a dist dist.bak

    say "собираю витрину..."
    if ! npm run build; then
        say "ОШИБКА: витрина не собралась"
        if [[ -d dist.bak ]]; then
            rm -rf dist
            mv dist.bak dist
            say "ОТКАТ: вернул предыдущую рабочую витрину, служба не тронута"
        fi
        exit 1
    fi

    rm -rf dist.bak
    cd "$STAND_DIR" || exit 1
    say "витрина собрана"
fi

main_pid="$(systemctl show -p MainPID --value "$STAND_UNIT" 2>/dev/null)"
if [[ -n "$main_pid" && "$main_pid" != "0" ]]; then
    kill "$main_pid" && say "двигатель перезапускается (systemd поднимет за ~5 с)"
else
    # Безобидно: служба сейчас в паузе перезапуска и стартует уже с новым кодом.
    say "ПРЕДУПРЕЖДЕНИЕ: процесс службы $STAND_UNIT не найден, перезапуск пропущен"
fi

say "готово"
