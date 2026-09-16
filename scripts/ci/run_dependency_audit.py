#!/usr/bin/env python3
"""SEC-64, разд. 64.1, строка «Vulnerable Components»: проверка зависимостей ЛОКАЛЬНО.

ЗАЧЕМ ЭТОТ ФАЙЛ. ТЗ требует «Trivy + pip-audit + npm audit в CI». Инструменты и
гейты к ним в проекте есть давно, но жили они ТОЛЬКО внутри CI, а CI выключен
вручную с 13.08.2026 по решению владельца (кончилась бесплатная квота минут).
Получилось худшее сочетание: проверка формально «есть», а на деле не выполнялась
ни разу больше месяца — и молчание выглядело как «всё хорошо».

ЧЕМ ЭТО КОНЧИЛОСЬ (16.09.2026, первый же запуск после паузы): 11 известных
уязвимостей в пяти пакетах на стороне сервера, среди них **боевая библиотека
шифрования** `cryptography` 49.0.0 с готовым исправлением, и **восемь
блокирующих** записей высокой важности на стороне витрины. Ни одна из них не
была видна, пока никто не запускал проверку.

РЕШЕНИЕ. Канонический гейт этого проекта — воспроизводимый ЛОКАЛЬНЫЙ прогон
(политика local-evidence). Значит, и проверка зависимостей должна запускаться
локально, одной командой, а не ждать включения CI:

    PYTHONPATH=backend python scripts/ci/run_dependency_audit.py

Скрипт делает три вещи и ничего не прячет:

1. Запускает ``pip-audit`` по УСТАНОВЛЕННОМУ окружению и ``npm audit`` по
   витрине.
2. Прогоняет находки через те же правила, что и CI: принятые записи из
   ``.github/security-exceptions.yml`` (у каждой — причина и СРОК), всё
   остальное — красный результат.
3. Записывает доказательство с датой в ``docs/security/DEPENDENCY_AUDIT_LOG.md``.

СРОК ГОДНОСТИ ПРОВЕРКИ. Сторож `tests/test_dependency_audit_freshness.py` валит
прогон, если последняя запись старше 30 дней. Это и есть главное решение среза:
**молчание больше не читается как «всё хорошо»** — оно читается как «проверку не
делали», и это видно на обычном прогоне тестов.

ЧЕСТНО О ГРАНИЦАХ. Обе проверки ходят в сеть (базы уязвимостей живут снаружи).
Без сети скрипт честно говорит, что проверить не смог, и НЕ притворяется
успешным. Trivy сканирует собранный образ и требует Docker — он остаётся за
пределами этого скрипта и запускается отдельно; здесь это сказано, а не умолчано.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "docs" / "security" / "DEPENDENCY_AUDIT_LOG.md"
EXCEPTIONS = REPO_ROOT / ".github" / "security-exceptions.yml"

#: Сколько дней проверка считается свежей. 30 — месяц: столько же длилась пауза,
#: за которую накопились 19 находок. Больше — и накопится столько же снова.
FRESH_DAYS = 30


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 600) -> tuple[int, str]:
    try:
        done = subprocess.run(
            cmd,
            cwd=cwd or REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"нет такой команды: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"превышено время ожидания ({timeout} с)"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _pip_audit(python: str) -> tuple[bool, str]:
    """Проверка пакетов сервера. Возвращает (всё ли чисто, что показать человеку)."""

    code, out = _run([python, "-m", "pip_audit", "--progress-spinner", "off"])
    if code == 127:
        return False, "pip-audit не установлен — проверить пакеты сервера НЕЧЕМ"
    if "ensurepip is not available" in out or "Failing command" in out:
        return False, "pip-audit не смог собрать окружение — проверка НЕ выполнена"
    if code == 0:
        return True, "pip-audit: известных уязвимостей нет"

    accepted = _accepted_ids("pip-audit")
    found = set(re.findall(r"\b(?:PYSEC|GHSA|CVE)[-A-Za-z0-9]+", out))
    blocking = sorted(found - accepted)
    if not blocking:
        return True, f"pip-audit: {len(found)} находок, все приняты записями с причиной и сроком"
    return False, "pip-audit: НЕ ПРИНЯТЫЕ находки: " + ", ".join(blocking)


def _npm_audit(tmp_json: Path, python: str) -> tuple[bool, str]:
    """Проверка пакетов витрины — тем же гейтом, что и в CI."""

    code, out = _run(["npm", "--prefix", "frontend", "audit", "--json"])
    if code == 127:
        return False, "npm не найден — проверить пакеты витрины НЕЧЕМ"
    payload = out[out.find("{") :] if "{" in out else ""
    try:
        json.loads(payload)
    except json.JSONDecodeError:
        return False, "npm audit не отдал разбираемый ответ — проверка НЕ выполнена"
    tmp_json.write_text(payload, encoding="utf-8")

    gate_code, gate_out = _run(
        [
            python,
            str(REPO_ROOT / "scripts" / "ci" / "check_npm_audit.py"),
            "--audit-json",
            str(tmp_json),
        ]
    )
    summary = next(
        (line for line in gate_out.splitlines() if line.startswith("npm-audit gate:")),
        "npm-audit gate: без сводки",
    )
    if gate_code == 0:
        return True, summary
    blocking = [line for line in gate_out.splitlines() if line.startswith("BLOCKING:")]
    return False, summary + "\n" + "\n".join(blocking[:10])


def _accepted_ids(tool: str) -> set[str]:
    """Принятые находки для инструмента: у каждой есть причина и срок."""

    try:
        import yaml  # noqa: PLC0415
    except ImportError:  # pragma: no cover - yaml есть в требованиях
        return set()
    data = yaml.safe_load(EXCEPTIONS.read_text(encoding="utf-8")) or {}
    return {
        str(item.get("id", "")).strip()
        for item in data.get("exceptions", [])
        if str(item.get("tool", "")).strip() == tool
    }


def _write_log(today: dt.date, lines: list[str], ok: bool) -> None:
    verdict = "ЧИСТО" if ok else "ЕСТЬ НЕ ПРИНЯТЫЕ НАХОДКИ"
    entry = [f"## {today.isoformat()} — {verdict}", ""]
    entry += [f"- {line}" for line in lines]
    entry += [
        "",
        "Trivy (образ) в этот прогон не входит: он требует Docker и запускается отдельно.",
        "",
    ]

    head = "# Журнал проверок зависимостей (SEC-64, разд. 64.1)\n\n"
    body = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else head
    body = body[len(head) :] if body.startswith(head) else body
    LOG_PATH.write_text(head + "\n".join(entry) + "\n" + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="каким Python звать pip-audit")
    parser.add_argument("--no-log", action="store_true", help="не записывать доказательство")
    args = parser.parse_args()

    tmp_json = REPO_ROOT / ".npm-audit.json"
    results: list[tuple[bool, str]] = [
        _pip_audit(args.python),
        _npm_audit(tmp_json, args.python),
    ]
    tmp_json.unlink(missing_ok=True)

    ok = all(good for good, _ in results)
    lines = [text for _, text in results]
    for line in lines:
        print(line)

    if not args.no_log:
        _write_log(dt.date.today(), lines, ok)
        print(f"\nдоказательство записано: {LOG_PATH.relative_to(REPO_ROOT)}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
