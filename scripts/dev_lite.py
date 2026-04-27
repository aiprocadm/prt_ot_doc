#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"
FRONTEND_DIR = ROOT_DIR / "frontend"
REQ_STAMP = VENV_DIR / ".requirements.stamp"
NPM_STAMP = FRONTEND_DIR / ".npm-ci.stamp"
ENV_FILE = ROOT_DIR / ".env"

ENV_UPDATES = {
    "APP_RUN_MODE": "dockerless",
    "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
    "STORAGE_BACKEND": "local",
    "S3_BACKEND": "local",
    "STORAGE_ROOT": "./.local_storage",
    "CELERY_EAGER": "true",
    "REDIS_URL": "memory://",
    "REDIS_RESULT_URL": "memory://",
    "RATE_LIMIT_STORAGE_URI": "memory://",
    "ENABLE_METRICS": "false",
    "LIBREOFFICE_BIN": "python",
    "DEMO_BOOTSTRAP": "0",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform dockerless dev launcher.")
    parser.add_argument("--preflight-only", action="store_true", help="Validate environment only.")
    parser.add_argument("--keep-db", action="store_true", help="Do not reset sqlite dev.db.")
    return parser.parse_args()


def parse_semver(text: str) -> tuple[int, int, int]:
    value = text.strip()
    if value.startswith("v"):
        value = value[1:]
    raw = value.split(".")
    if len(raw) < 2:
        raise RuntimeError(f"Cannot parse version: {text}")
    major = int(raw[0])
    minor = int(raw[1])
    patch = 0
    if len(raw) > 2:
        token = "".join(ch for ch in raw[2] if ch.isdigit())
        patch = int(token) if token else 0
    return major, minor, patch


def assert_min_version(current: tuple[int, int, int], minimum: tuple[int, int, int], label: str) -> None:
    if current < minimum:
        raise RuntimeError(f"{label} {current[0]}.{current[1]}.{current[2]} is unsupported; need {minimum[0]}.{minimum[1]}+")


def run_checked(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def command_output(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout.strip() or proc.stderr.strip()


def get_venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def is_port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def update_env_file() -> None:
    if not ENV_FILE.exists():
        shutil.copy(ROOT_DIR / ".env.example", ENV_FILE)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        if key in ENV_UPDATES:
            new_lines.append(f"{key}={ENV_UPDATES[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, value in ENV_UPDATES.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def ensure_python_env() -> Path:
    venv_python = get_venv_python()
    if not venv_python.exists():
        run_checked([sys.executable, "-m", "venv", str(VENV_DIR)])
    return venv_python


def ensure_python_deps(venv_python: Path) -> None:
    if (
        not REQ_STAMP.exists()
        or (ROOT_DIR / "requirements.txt").stat().st_mtime > REQ_STAMP.stat().st_mtime
        or (ROOT_DIR / "requirements-dev.txt").stat().st_mtime > REQ_STAMP.stat().st_mtime
    ):
        run_checked([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
        run_checked([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt"])
        REQ_STAMP.touch()
    else:
        print("Python dependencies are up to date (.venv).")


def ensure_frontend_deps() -> None:
    vite_bin = FRONTEND_DIR / "node_modules" / ".bin" / ("vite.cmd" if os.name == "nt" else "vite")
    need_install = (
        not (FRONTEND_DIR / "node_modules").exists()
        or not NPM_STAMP.exists()
        or not vite_bin.exists()
        or (FRONTEND_DIR / "package-lock.json").stat().st_mtime > NPM_STAMP.stat().st_mtime
    )
    if not need_install:
        print("Frontend dependencies are up to date (frontend/node_modules).")
        return
    try:
        run_checked(["npm", "ci"], cwd=FRONTEND_DIR)
    except subprocess.CalledProcessError:
        print("WARNING: npm ci failed; cleaning node_modules and retrying once.")
        shutil.rmtree(FRONTEND_DIR / "node_modules", ignore_errors=True)
        run_checked(["npm", "ci"], cwd=FRONTEND_DIR)
    NPM_STAMP.touch()


def healthcheck(url: str, timeout_s: int = 60) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def preflight() -> None:
    py_version_text = command_output([sys.executable, "--version"]).replace("Python", "").strip()
    py_ver = parse_semver(py_version_text)
    assert_min_version(py_ver, (3, 12, 0), "Python")

    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js not found in PATH. Install Node.js LTS (>=18.18).")
    node_version_text = command_output([node, "--version"])
    assert_min_version(parse_semver(node_version_text), (18, 18, 0), "Node.js")

    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found in PATH. Reinstall Node.js LTS.")
    npm_version_text = command_output([npm, "--version"])
    assert_min_version(parse_semver(npm_version_text), (9, 0, 0), "npm")

    print(f"Preflight OK: Python {py_version_text}, Node {node_version_text}, npm {npm_version_text}")


def build_runtime_env(venv_python: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_RUN_MODE": "dockerless",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "STORAGE_BACKEND": "local",
            "S3_BACKEND": "local",
            "STORAGE_ROOT": "./.local_storage",
            "CELERY_EAGER": "true",
            "REDIS_URL": "memory://",
            "REDIS_RESULT_URL": "memory://",
            "RATE_LIMIT_STORAGE_URI": "memory://",
            "ENABLE_METRICS": "false",
            "LIBREOFFICE_BIN": str(venv_python),
            "DEMO_BOOTSTRAP": "0",
        }
    )
    return env


def main() -> int:
    os.chdir(ROOT_DIR)
    args = parse_args()
    preflight()
    if args.preflight_only:
        return 0

    venv_python = ensure_python_env()
    update_env_file()
    ensure_python_deps(venv_python)
    ensure_frontend_deps()

    if is_port_busy(8000):
        raise RuntimeError("Backend port 8000 is already in use. Stop existing process and retry.")
    if is_port_busy(5173):
        raise RuntimeError("Frontend port 5173 is already in use. Stop existing process and retry.")

    if not args.keep_db:
        db_file = ROOT_DIR / "dev.db"
        if db_file.exists():
            db_file.unlink()

    env = build_runtime_env(venv_python)
    print("\nDockerless mode enabled")
    print(f"- Database: {env['DATABASE_URL']}")
    print(f"- Storage: {env['STORAGE_BACKEND']} ({env['STORAGE_ROOT']})")
    print(f"- Celery eager: {env['CELERY_EAGER']}")
    print("- Redis: disabled")
    print("\nBackend:  http://localhost:8000")
    print("Frontend: http://localhost:5173\n")

    backend = subprocess.Popen([str(venv_python), "./scripts/run_backend_lite.py"], cwd=ROOT_DIR, env=env)
    frontend: subprocess.Popen[str] | None = None

    def stop_all() -> None:
        for proc in (frontend, backend):
            if proc and proc.poll() is None:
                proc.terminate()
        for proc in (frontend, backend):
            if proc:
                try:
                    proc.wait(timeout=8)
                except Exception:
                    proc.kill()

    def _signal_handler(_sig: int, _frame: object) -> None:
        stop_all()
        raise SystemExit(130)

    signal.signal(signal.SIGINT, _signal_handler)
    if platform.system() != "Windows":
        signal.signal(signal.SIGTERM, _signal_handler)

    try:
        if healthcheck("http://127.0.0.1:8000/health"):
            print("Backend ready: http://127.0.0.1:8000/health")
        else:
            print("WARNING: Backend health check timed out (continuing; inspect backend logs).")
        frontend = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"],
            cwd=FRONTEND_DIR,
            env=os.environ.copy(),
        )
        while True:
            if backend.poll() is not None:
                return backend.returncode or 0
            if frontend.poll() is not None:
                return frontend.returncode or 0
            time.sleep(0.5)
    finally:
        stop_all()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed ({exc.returncode}): {' '.join(exc.cmd)}", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
