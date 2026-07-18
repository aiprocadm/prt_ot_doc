#!/usr/bin/env python3
"""Локальный воспроизводимый гейт качества (REL-1) — без GitHub Actions.

GitHub Actions на репозитории отключены/недоступны как живой gate
(см. docs/stabilization/RELEASE_BLOCKERS_STATUS.md). Этот скрипт даёт
*воспроизводимый* эквивалент CI-джобы `backend-tests` на любой машине, где
есть Docker: он поднимает PostgreSQL 16 и гоняет бэкенд-тесты внутри образа
с Python 3.12 (см. scripts/ci/Dockerfile.gate), а НЕ на хостовом Python.

Почему через Docker, а не на хосте: репозиторий требует Python 3.12.12, на
3.13+/Windows pytest зависает на сборе (см. CLAUDE.md). Контейнер фиксирует
версию Python и системные зависимости — это и есть «воспроизводимость».

Режимы:
  --db-only   (по умолчанию) только PG-критичный срез: `alembic upgrade heads`
              на чистом PG16 + все тесты с маркером `db` (enum label-drift
              guards, downgrade round-trip). Быстро, высокий сигнал — закрывает
              REL-2 / REL-3 по существу.
  --full      полный бэкенд-suite с TEST_PG_ADMIN_URL (зеркало CI backend-tests).
              Долго; часть рендер-тестов требует LibreOffice (нет в gate-образе)
              и может пропускаться/падать — это ожидаемо, см. policy-док.

Артефакт: пишет JSON-вердикт в artifacts/local-gate/summary.json
(reproducible-evidence по политике из docs/stabilization/local-evidence-gate.md).

Примеры:
  python scripts/ci/local_gate.py                 # db-only
  python scripts/ci/local_gate.py --full
  python scripts/ci/local_gate.py --keep-db        # не гасить PG после прогона
  python scripts/ci/local_gate.py -- -k enum -x    # доп. аргументы pytest
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_DOCKERFILE = REPO_ROOT / "scripts" / "ci" / "Dockerfile.gate"
GATE_IMAGE = "ptd-local-gate:py312"
PG_IMAGE = "postgres:16"
PG_USER = "ptd"
PG_PASSWORD = "ptd"
PG_DB = "ptd"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "local-gate"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Запуск с эхом команды; по умолчанию НЕ глушит вывод."""
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, **kw)


def _docker_available() -> bool:
    try:
        return (
            _run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
            ).returncode
            == 0
        )
    except FileNotFoundError:
        return False


def build_gate_image() -> None:
    print("\n=== Сборка gate-образа (кэшируется по requirements*.txt) ===")
    # Минимальный build-context: только манифесты зависимостей. Так в демон
    # не уезжает всё дерево репозитория (prt_ot_doc-main, artifacts, dev.db и т.п.),
    # а слой pip-install кэшируется ровно по этим двум файлам.
    with tempfile.TemporaryDirectory(prefix="ptd-gate-ctx-") as ctx:
        ctx_path = Path(ctx)
        for fname in ("requirements.txt", "requirements-dev.txt"):
            shutil.copy2(REPO_ROOT / fname, ctx_path / fname)
        shutil.copy2(GATE_DOCKERFILE, ctx_path / "Dockerfile")
        res = _run(
            [
                "docker",
                "build",
                "-f",
                str(ctx_path / "Dockerfile"),
                "-t",
                GATE_IMAGE,
                str(ctx_path),
            ]
        )
    if res.returncode != 0:
        raise SystemExit("Не удалось собрать gate-образ")


def start_postgres(network: str, name: str) -> None:
    print("\n=== Запуск PostgreSQL 16 ===")
    _run(["docker", "network", "create", network], capture_output=True, text=True)
    res = _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "-e",
            f"POSTGRES_USER={PG_USER}",
            "-e",
            f"POSTGRES_PASSWORD={PG_PASSWORD}",
            "-e",
            f"POSTGRES_DB={PG_DB}",
            PG_IMAGE,
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Не удалось запустить PostgreSQL: {res.stderr}")


def wait_for_postgres(name: str, timeout_s: int = 120) -> None:
    print("=== Ожидание готовности PostgreSQL (pg_isready) ===")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = subprocess.run(
            ["docker", "exec", name, "pg_isready", "-U", PG_USER, "-d", PG_DB],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print("PostgreSQL готов.")
            return
        time.sleep(2)
    raise SystemExit("PostgreSQL не поднялся за отведённое время")


# PG-критичные тест-файлы (db-only режим). Каждый сам создаёт/дропает throwaway-БД
# через TEST_PG_ADMIN_URL и сам скипается, если он не задан:
#  - test_alembic_postgres_upgrade.py — upgrade heads + downgrade base round-trip на PG16
#  - test_orm_enum_pg_label_parity.py — keystone enum label-drift guard + write-smoke (live PG)
#  - test_orm_enum_values_callable_parity.py — быстрый пин Group-A (без PG, но enum-релевантен)
# Прямое перечисление файлов вместо `-m db` по всему дереву: без сборки всего suite
# (она могла бы упасть на импортах в образе без LibreOffice) и без риска SQLite-фолбэка.
PG_GATE_FILES = (
    "backend/tests/test_alembic_postgres_upgrade.py",
    "backend/tests/test_orm_enum_pg_label_parity.py",
    "backend/tests/test_orm_enum_values_callable_parity.py",
)


def gate_command(mode: str, extra_pytest: list[str], pg_name: str) -> str:
    """Команда, исполняемая внутри gate-контейнера (bash -c)."""
    # PYTHONPATH=/srv/backend нужен alembic-инвокации; для pytest он зашит в
    # pyproject (pythonpath=["backend","."]).
    extra = " ".join(extra_pytest)
    pg_async = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{pg_name}:5432/{PG_DB}"
    steps = [
        "set -e",
        "export PYTHONPATH=/srv/backend",
        # ARCH-3: границы bounded-context. Быстро, без PG (stdlib AST-чекер).
        # Падает на НОВОМ cross-context импорте; текущие протечки в allowlist.
        'echo "--- check-boundaries: границы bounded-context (ARCH-3) ---"',
        "python scripts/ci/check_context_boundaries.py",
    ]
    if mode == "db-only":
        steps += [
            'echo "--- PG-критичный срез: alembic upgrade/downgrade на PG16 + enum guards ---"',
            f"pytest -p no:cacheprovider -rfE --tb=short {' '.join(PG_GATE_FILES)} {extra}",
        ]
    else:  # full
        steps += [
            'echo "--- [1/2] alembic upgrade heads на чистом PG16 (зеркало job alembic-postgres-upgrade) ---"',
            # DATABASE_URL=PG задаём ТОЛЬКО для alembic-шага. Полный pytest ниже
            # идёт на SQLite + throwaway-PG (через TEST_PG_ADMIN_URL) — как в CI
            # backend-tests, где глобального DATABASE_URL нет.
            f"DATABASE_URL={pg_async} alembic -c backend/app/migrations/alembic.ini upgrade heads",
            'echo "--- [2/2] полный бэкенд-suite (зеркало CI backend-tests) ---"',
            f"pytest -p no:cacheprovider --timeout=300 -rfE --tb=short {extra}",
        ]
    return "\n".join(steps)


def run_gate(mode: str, network: str, pg_name: str, extra_pytest: list[str]) -> int:
    print(f"\n=== Прогон гейта (режим: {mode}) ===")
    admin_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@{pg_name}:5432/{PG_DB}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "-v",
        f"{REPO_ROOT}:/srv",
        "-w",
        "/srv",
        "-e",
        "APP_ENV=test",
        "-e",
        "REDIS_URL=memory://",
        "-e",
        "REDIS_RESULT_URL=cache+memory://",
        "-e",
        "RATE_LIMIT_STORAGE_URI=memory://",
        "-e",
        "S3_ENDPOINT=http://localhost",
        "-e",
        "SECRET_KEY=local-gate-not-for-production",
        # TEST_PG_ADMIN_URL включает @pytest.mark.db гарды; throwaway-БД они
        # создают/дропают сами (enum_*<uuid>), основной `ptd` не трогается.
        "-e",
        f"TEST_PG_ADMIN_URL={admin_url}",
        GATE_IMAGE,
        "bash",
        "-c",
        gate_command(mode, extra_pytest, pg_name),
    ]
    return _run(cmd).returncode


def teardown(network: str, pg_name: str) -> None:
    print("\n=== Остановка PostgreSQL ===")
    subprocess.run(["docker", "rm", "-f", pg_name], capture_output=True, text=True)
    subprocess.run(["docker", "network", "rm", network], capture_output=True, text=True)


def write_summary(mode: str, exit_code: int, started: str) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / "summary.json"
    payload = {
        "gate": "local-evidence",
        "mode": mode,
        "verdict": "green" if exit_code == 0 else "red",
        "exit_code": exit_code,
        "python": "3.12 (gate image)",
        "postgres": PG_IMAGE,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "command": f"python scripts/ci/local_gate.py --{mode}",
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--db-only",
        action="store_const",
        dest="mode",
        const="db-only",
        help="только PG-критичный срез (по умолчанию)",
    )
    g.add_argument(
        "--full",
        action="store_const",
        dest="mode",
        const="full",
        help="полный бэкенд-suite (зеркало CI)",
    )
    parser.add_argument(
        "--keep-db", action="store_true", help="не гасить PostgreSQL после прогона (для отладки)"
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="не пересобирать gate-образ (использовать существующий)",
    )
    parser.add_argument("pytest_args", nargs="*", help="доп. аргументы pytest после --")
    parser.set_defaults(mode="db-only")
    args = parser.parse_args()

    if not _docker_available():
        print(
            "ОШИБКА: Docker недоступен. Этот гейт требует Docker "
            "(PostgreSQL 16 + python:3.12 раннер).",
            file=sys.stderr,
        )
        return 2

    started = datetime.now(timezone.utc).isoformat()
    suffix = uuid.uuid4().hex[:8]
    network = f"ptd-gate-net-{suffix}"
    pg_name = f"ptd-gate-pg-{suffix}"

    exit_code = 1
    try:
        if not args.no_build:
            build_gate_image()
        start_postgres(network, pg_name)
        wait_for_postgres(pg_name)
        exit_code = run_gate(args.mode, network, pg_name, args.pytest_args)
    finally:
        if args.keep_db:
            print(
                f"\n[--keep-db] PostgreSQL оставлен запущенным: {pg_name} "
                f"(сеть {network}). Удалить: docker rm -f {pg_name} && "
                f"docker network rm {network}"
            )
        else:
            teardown(network, pg_name)

    summary = write_summary(args.mode, exit_code, started)
    verdict = "ЗЕЛЁНЫЙ ✅" if exit_code == 0 else "КРАСНЫЙ ❌"
    print(f"\n=== Вердикт гейта: {verdict} (exit={exit_code}) ===")
    print(f"Артефакт: {summary}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
