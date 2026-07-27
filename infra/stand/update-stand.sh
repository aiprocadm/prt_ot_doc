#!/usr/bin/env bash
# Автообновление тестового стенда до свежей ветки main (docs/RUNBOOK_TEST_STAND.md).
#
# Стенд работает из ОТДЕЛЬНОЙ копии репозитория, а не из рабочей папки разработки:
# иначе соседняя сессия своей обычной работой (сборка, смена ветки, установка
# зависимостей) оставляет стенд без витрины и он уходит в цикл падений. На этом
# сервере такое уже приводило к простою в несколько суток, причём внешне
# выглядело сетевой проблемой.
#
# Главный принцип: стенд НИКОГДА не остаётся без рабочей витрины. Перед
# пересборкой снимается копия frontend/dist, и при любой осечке (зависимости,
# сборка) всё откатывается на предыдущее рабочее состояние, а служба не трогается.
#
# Схему SQLite приложение создаёт само при старте (prepare_runtime → create_all),
# поэтому alembic здесь не гоняется. Появление НОВЫХ таблиц подхватывается само;
# изменение колонок в существующих — нет. Если после обновления посыпались ошибки
# про отсутствующую колонку, стенду нужна свежая база: остановить службу, удалить
# dev.db, запустить — схема создастся заново, демо-данные засеются (DEMO_BOOTSTRAP).
#
# Зависимости: git, uv (ставит Python-зависимости), node/npm, flock, systemd.
# sudo НЕ нужен: служба объявлена с User=aiproc, поэтому перезапуск делается
# сигналом своему же процессу, а Restart=always поднимет её обратно.
#
# Env:
#   STAND_DIR       — папка отдельной копии (default /home/aiproc/stands/prt_ot_doc)
#   STAND_BRANCH    — какую ветку показывать (default main)
#   STAND_UNIT      — служба двигателя (default ptd-doc-web)
#   STAND_LOG       — журнал обновлений (default <STAND_DIR>/../logs/doc-update.log)
#   STAND_NODE_BIN  — папка с node/npm (default /home/aiproc/.nvm/versions/node/v24.18.0/bin)
#   STAND_UV        — путь к uv (default /home/aiproc/.local/bin/uv)
#
# Установка в cron (пользователь, от которого работают службы; НЕ root):
#   */10 * * * * /home/aiproc/stands/prt_ot_doc/infra/stand/update-stand.sh
#
# Нового коммита нет — скрипт молча выходит. Ручной запуск безопасен.

# ВАЖНО: здесь намеренно НЕ `set -e`. Скрипт обязан сам перехватывать ошибки
# каждого шага и делать откат, а не умирать на первой из них.
set -uo pipefail

STAND_DIR="${STAND_DIR:-/home/aiproc/stands/prt_ot_doc}"
STAND_BRANCH="${STAND_BRANCH:-main}"
STAND_UNIT="${STAND_UNIT:-ptd-doc-web}"
STAND_LOG="${STAND_LOG:-$(dirname "$STAND_DIR")/logs/doc-update.log}"
STAND_NODE_BIN="${STAND_NODE_BIN:-/home/aiproc/.nvm/versions/node/v24.18.0/bin}"
STAND_UV="${STAND_UV:-/home/aiproc/.local/bin/uv}"

# Скрипт лежит ВНУТРИ той самой копии, которую сам же перезаписывает через
# `git reset --hard`. Bash дочитывает файл по ходу выполнения, поэтому подмена
# файла на середине приводит к непредсказуемому поведению. Поэтому первым делом
# переезжаем на временную копию себя и работаем уже с неё.
if [[ "${STAND_SELF_EXEC:-}" != "1" ]]; then
    self_copy="$(mktemp)" || exit 1
    cp "$0" "$self_copy" || { rm -f "$self_copy"; exit 1; }
    chmod +x "$self_copy"
    STAND_SELF_EXEC=1 exec "$self_copy" "$@"
fi
# Удаляем временную копию сразу: файл уже открыт, и Linux даст дочитать его
# до конца по существующему дескриптору, а мусор после себя мы не оставим.
rm -f "$0"

export PATH="$STAND_NODE_BIN:$PATH"
mkdir -p "$(dirname "$STAND_LOG")"

log() { echo "$(date '+%F %T') $*" >>"$STAND_LOG"; }

# Сборка длится дольше, чем промежуток между запусками по расписанию,
# поэтому запуски не должны накладываться друг на друга.
exec 9>"${STAND_DIR}.update.lock"
if ! flock -n 9; then
    log "предыдущее обновление ещё идёт — пропускаю этот запуск"
    exit 0
fi

cd "$STAND_DIR" || { log "ОШИБКА: нет папки $STAND_DIR"; exit 1; }

if ! git fetch --depth=1 origin "$STAND_BRANCH" --quiet 2>>"$STAND_LOG"; then
    log "ОШИБКА: не удалось получить обновления с GitHub"
    exit 1
fi

prev="$(git rev-parse HEAD)"
target="$(git rev-parse "origin/$STAND_BRANCH")"

if [[ "$prev" == "$target" ]]; then
    exit 0   # нового кода нет — обычный случай, молчим
fi

log "новый код ${prev:0:8} -> ${target:0:8}, начинаю обновление"

# Снимок рабочей витрины — страховка на случай неудачи.
rm -rf frontend/dist.bak
[[ -d frontend/dist ]] && cp -a frontend/dist frontend/dist.bak

rollback() {
    log "ОТКАТ: возвращаю предыдущую рабочую версию ${prev:0:8}"
    git reset --hard "$prev" --quiet 2>>"$STAND_LOG"
    if [[ -d frontend/dist.bak ]]; then
        rm -rf frontend/dist
        mv frontend/dist.bak frontend/dist
    fi
    log "откат завершён, стенд продолжает работать на старой версии"
}

py_before="$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1)"
js_before="$(md5sum frontend/package-lock.json 2>/dev/null | cut -d' ' -f1)"

if ! git reset --hard "$target" --quiet 2>>"$STAND_LOG"; then
    log "ОШИБКА: не удалось переключить код"
    rollback
    exit 1
fi

py_after="$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1)"
js_after="$(md5sum frontend/package-lock.json 2>/dev/null | cut -d' ' -f1)"

# Зависимости переустанавливаем только если список реально изменился —
# иначе это лишние минуты на каждом обновлении.
if [[ "$py_before" != "$py_after" ]]; then
    log "изменился requirements.txt — переустанавливаю зависимости Python"
    if ! "$STAND_UV" pip install -r requirements.txt --python .venv/bin/python >>"$STAND_LOG" 2>&1; then
        log "ОШИБКА: не встали зависимости Python"
        rollback
        exit 1
    fi
fi

if [[ "$js_before" != "$js_after" ]]; then
    log "изменился frontend/package-lock.json — переустанавливаю зависимости фронтенда"
    if ! (cd frontend && npm ci) >>"$STAND_LOG" 2>&1; then
        log "ОШИБКА: не встали зависимости фронтенда"
        rollback
        exit 1
    fi
fi

if ! (cd frontend && npm run build) >>"$STAND_LOG" 2>&1; then
    log "ОШИБКА: витрина не собралась"
    rollback
    exit 1
fi

rm -rf frontend/dist.bak

main_pid="$(systemctl show -p MainPID --value "$STAND_UNIT" 2>/dev/null)"
if [[ -n "$main_pid" && "$main_pid" != "0" ]]; then
    kill "$main_pid" 2>>"$STAND_LOG"
else
    # Безобидно: служба сейчас в паузе перезапуска и стартует уже с новым кодом.
    log "ПРЕДУПРЕЖДЕНИЕ: не нашёл процесс службы $STAND_UNIT, перезапуск пропущен"
fi

log "готово: стенд обновлён до ${target:0:8} — $(git log -1 --format='%s' | head -c 80)"
