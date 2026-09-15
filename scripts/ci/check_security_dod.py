#!/usr/bin/env python3
"""Гейт «седьмого вопроса» безопасности (SEC-69, Доп.№3 разд. 69.3).

ЧТО БЫЛО. Вопрос «какие новые поверхности атаки вводит фича и как они закрыты?»
был записан константой ``SECURITY_QUESTION`` и пунктом шаблона PR. Отдельный
тест следил, чтобы формулировки совпадали дословно. Но ГЕЙТА не было: галочку
можно было не ставить, и ничего не происходило. Строка матрицы так и писала:
«константа есть, гейта нет; ввод меняет процесс ревью, поэтому предложен, а не
навязан».

РЕШЕНИЕ (2026-09-14, делегировано владельцем). Навязать — но умно. Требовать
ответ на КАЖДЫЙ PR означало бы ритуал: правка опечатки в документации тоже
«вводит поверхности». Поэтому гейт сначала смотрит, ЧТО тронуто, и спрашивает
только там, где поверхность действительно могла появиться.

КАК РАБОТАЕТ.

1. Берёт список изменённых файлов относительно базы (``--base``, по умолчанию
   ``origin/main``) или готовый список (``--files-from``).
2. Раскладывает их по поверхностям (ручки, миграции, приём файлов, промежуточные
   слои, внешний контур, вебхуки, права, зависимости).
3. Поверхностей нет — проверка пройдена молча.
4. Поверхности есть — в описании PR обязан стоять отмеченный пункт Security DoD.
   Описание берётся из ``--body-file`` или переменной ``PR_BODY``.

ПОЧЕМУ НЕ ПРОСТО «ГАЛОЧКА ПОСТАВЛЕНА». Галочка без текста — это ритуал.
Требуется одно из двух: либо галочка стоит и под ней есть непустой ответ, либо
явно написано «нет новых поверхностей». Второе тоже решение, но осознанное.

ЗАПУСК ВРУЧНУЮ::

    PYTHONPATH=backend python scripts/ci/check_security_dod.py \
        --base origin/main --body-file /tmp/pr.md
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Поверхности атаки: (имя для человека, правила отбора путей).
#: Правило — префикс пути или подстрока имени файла. Список намеренно
#: КОНСЕРВАТИВНЫЙ: лучше спросить лишний раз, чем пропустить новую ручку.
SURFACES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ручки API", ("backend/app/api/routes/", "backend/app/api/deps/")),
    ("миграции базы", ("backend/app/migrations/",)),
    ("промежуточные слои запроса", ("backend/app/middleware/",)),
    (
        "приём и разбор файлов",
        (
            "backend/app/modules/files/",
            "backend/app/core/archive_safety.py",
            "backend/app/core/xml_security.py",
        ),
    ),
    (
        "внешний контур",
        (
            "backend/app/core/external_perimeter.py",
            "backend/app/api/routes/client_portal",
            "backend/app/api/routes/public_signup.py",
        ),
    ),
    (
        "вебхуки и интеграции",
        (
            "backend/app/services/webhooks.py",
            "backend/app/core/inbound_webhook_auth.py",
            "backend/app/core/ssrf_guard.py",
        ),
    ),
    (
        "права и доступ",
        (
            "backend/app/modules/rbac_abac/",
            "backend/app/core/security.py",
            "backend/app/core/permissions",
        ),
    ),
    (
        "секреты и ключи",
        ("backend/app/core/secret_cipher.py", "backend/app/core/key_provider.py"),
    ),
    (
        # Срез-210 добавил эту поверхность, применив гейт к собственному PR:
        # правка чинила ВНЕДРЕНИЕ В ЗАПРОС (значение из заголовка попадало в
        # текст SQL) — и гейт НЕ СПРОСИЛ НИЧЕГО, потому что слой доступа к базе
        # в списке не значился. Здесь живут маршрутизация по схемам арендатора,
        # второй рубеж изоляции (RLS) и сборка запросов — ошибка тут стоит
        # дороже, чем в любой отдельной ручке.
        "слой доступа к базе",
        ("backend/app/db/", "backend/app/core/sql_text.py", "backend/app/core/rls_policy.py"),
    ),
)

#: Поверхность «зависимости» отбирается ИНАЧЕ — по ИМЕНИ ФАЙЛА целиком, а не по
#: куску пути.
#:
#: ПОЧЕМУ. Первая версия искала подстроку «requirements», и любой файл раздела
#: «требования по НПА» (`compliance_requirements.py`, `test_..._requirements...`)
#: срабатывал как «изменены зависимости». Нашлось это применением гейта к
#: собственному PR среза-195: он честно потребовал ответ про зависимости там, где
#: не менялся ни один манифест. Сторож, который кричит не по делу, перестают
#: читать — ровно то, от чего этот гейт и защищает.
DEPENDENCY_FILES: frozenset[str] = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "poetry.lock",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
)
DEPENDENCY_SURFACE = "зависимости"

#: Осознанный ответ «поверхностей нет». Дословность не требуется — важно, чтобы
#: человек написал это словами, а не молча пропустил пункт.
NO_SURFACE_RE = re.compile(r"нет\s+новых\s+поверхн", re.IGNORECASE)

#: Отмеченный пункт чек-листа: ``- [x]`` в любом регистре.
TICKED_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.+)$")

#: Сколько осмысленного текста считаем ответом. Одно слово «да» — не ответ.
MIN_ANSWER_CHARS = 12


def _security_question() -> str:
    """Формулировка вопроса из кода — единый источник с шаблоном PR."""

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.product_spec import SECURITY_QUESTION  # noqa: PLC0415

    return SECURITY_QUESTION


def _changed_files(base: str, files_from: str | None) -> list[str]:
    if files_from:
        raw = Path(files_from).read_text(encoding="utf-8")
        return [line.strip() for line in raw.splitlines() if line.strip()]
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit("ERROR: git не найден; передайте список файлов через --files-from")
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise SystemExit(
            f"ERROR: не удалось сравнить с базой {base!r}: {stderr}\n"
            "Укажите другую базу через --base или список файлов через --files-from."
        )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def touched_surfaces(paths: list[str]) -> list[str]:
    """Какие поверхности атаки затронуты изменёнными файлами."""

    normalized = [path.replace("\\", "/") for path in paths]
    found: list[str] = []
    for name, rules in SURFACES:
        if any(rule in path for path in normalized for rule in rules):
            found.append(name)
    # Манифесты зависимостей — по имени файла целиком (см. DEPENDENCY_FILES).
    if any(path.rsplit("/", 1)[-1] in DEPENDENCY_FILES for path in normalized):
        found.append(DEPENDENCY_SURFACE)
    return found


def _pr_body(body_file: str | None) -> str | None:
    if body_file:
        path = Path(body_file)
        if not path.exists():
            raise SystemExit(f"ERROR: файл описания не найден: {path}")
        return path.read_text(encoding="utf-8")
    env = os.environ.get("PR_BODY")
    return env if env else None


def _norm(text: str) -> str:
    """Убрать разметку выделения и лишние пробелы: вопрос в шаблоне набран жирным."""

    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", "")).strip()


def answer_in_body(body: str, question: str) -> tuple[bool, str]:
    """Есть ли в описании осознанный ответ на седьмой вопрос.

    Возвращает ``(ответ_есть, причина_отказа)``.
    """

    if NO_SURFACE_RE.search(body):
        return True, ""

    # Ищем ОТМЕЧЕННЫЙ пункт, в котором звучит сам вопрос.
    #
    # Отрезать надо ВЕСЬ вопрос, а не его начало: иначе хвост самой формулировки
    # («…и как они закрыты?») засчитывается как ответ, и галочка без текста
    # проходит гейт. Ровно на этом первая версия и попалась.
    needle = _norm(question).lower()
    lines = body.splitlines()
    for index, line in enumerate(lines):
        match = TICKED_RE.match(line)
        if not match:
            continue
        text = _norm(match.group(1))
        if needle not in text.lower():
            continue
        # Ответ — либо продолжение самой строки после вопроса, либо строки под ней
        # до следующего пункта/заголовка.
        cut = text.lower().index(needle) + len(needle)
        answer = re.sub(r"[^\w\s]", " ", text[cut:], flags=re.UNICODE).strip()
        for following in lines[index + 1 :]:
            if TICKED_RE.match(following) or following.lstrip().startswith(("#", "- [ ]", "* [ ]")):
                break
            answer = f"{answer} {following.strip()}"
        answer = " ".join(answer.split())
        if len(answer) < MIN_ANSWER_CHARS:
            return False, (
                "пункт Security DoD отмечен, но ответа под ним нет. "
                "Галочка без текста — ритуал, а не проверка: напишите, какие ручки, "
                "параметры, файлы или вебхуки появились, кто имеет к ним доступ и чем "
                "ограничен перебор."
            )
        return True, ""

    return False, (
        "в описании PR не отмечен пункт Security DoD с седьмым вопросом. "
        "Если поверхностей действительно нет — напишите словами «нет новых поверхностей»: "
        "это тоже решение, но осознанное."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="С чем сравнивать (ветка/коммит).")
    parser.add_argument("--files-from", default=None, help="Файл со списком изменённых путей.")
    parser.add_argument("--body-file", default=None, help="Файл с описанием PR (или PR_BODY).")
    args = parser.parse_args()

    question = _security_question()
    paths = _changed_files(args.base, args.files_from)
    surfaces = touched_surfaces(paths)

    if not surfaces:
        print("Security DoD: изменения не трогают поверхности атаки — вопрос не задаётся.")
        return 0

    listed = ", ".join(sorted(set(surfaces)))
    body = _pr_body(args.body_file)
    if body is None:
        print(
            "ERROR: изменения трогают поверхности атаки "
            f"({listed}), а описание PR не передано.\n"
            "Передайте его через --body-file или переменную PR_BODY.",
            file=sys.stderr,
        )
        return 1

    ok, reason = answer_in_body(body, question)
    if not ok:
        print(
            f"ERROR: изменения трогают поверхности атаки ({listed}).\n"
            f"Вопрос: {question}\n"
            f"Причина отказа: {reason}",
            file=sys.stderr,
        )
        return 1

    print(f"Security DoD: поверхности ({listed}) — ответ в описании PR есть.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
