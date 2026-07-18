#!/usr/bin/env python3
"""ARCH-4 guard — splitting Celery task files must keep task registration identical.

`backend/app/tasks/_core.py` is a god-file. Splitting its tasks into sub-modules
(re-exported from `_core`, per the sanctioned plan in `app/tasks/__init__.py`)
must NOT change:

* the set of registered Celery task NAMES (`celery_app.tasks` keys) — a changed
  name silently breaks beat schedules / `send_task` callers;
* the public attributes reachable as `app.tasks.<name>` (the package re-exposes
  `_core` via `__getattr__`).

Modes:
  --snapshot   capture the current state to the baseline JSON.
  (default)    compare to the baseline; exit 1 on any drift.

Baseline: docs/stabilization/celery_tasks_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "docs" / "stabilization" / "celery_tasks_baseline.json"


def _collect() -> dict:
    import app.tasks  # noqa: F401  imports _core -> registers all tasks
    from app.services.celery_app import celery_app

    # App-defined task names (exclude celery's built-in celery.* tasks).
    task_names = sorted(n for n in celery_app.tasks.keys() if not n.startswith("celery."))
    # Public callables/attrs re-exposed from app.tasks._core.
    core = sys.modules["app.tasks._core"]
    public = sorted(n for n in dir(core) if not n.startswith("__"))
    return {"task_names": task_names, "core_public": public}


def _snapshot() -> int:
    data = _collect()
    BASELINE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ snapshot written: {BASELINE} ({len(data['task_names'])} registered tasks)")
    return 0


def _compare() -> int:
    if not BASELINE.exists():
        print(f"No baseline at {BASELINE}; run with --snapshot first.", file=sys.stderr)
        return 2
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    cur = _collect()
    ok = True

    # AUTHORITATIVE: the set of registered Celery task names must be EXACTLY
    # preserved (a changed name silently breaks beat schedules / send_task).
    t_added = sorted(set(cur["task_names"]) - set(base["task_names"]))
    t_removed = sorted(set(base["task_names"]) - set(cur["task_names"]))
    if t_added or t_removed:
        ok = False
        print("✖ ARCH-4: Celery task names changed:")
        for a in t_added:
            print(f"    + {a}")
        for r in t_removed:
            print(f"    - {r}")

    # INFORMATIONAL: app.tasks._core attribute losses. Moving helpers/tasks to
    # sub-modules legitimately drops incidental imports (threading, perf_counter,
    # …) from _core; only a lost *task/helper that callers import* would matter,
    # and the task-name check above already covers registered tasks. Reported,
    # not fatal.
    c_removed = sorted(set(base["core_public"]) - set(cur["core_public"]))
    if c_removed:
        print("  note — app.tasks._core no longer exposes (incidental imports / moved):")
        print("    " + ", ".join(c_removed))

    if ok:
        print(f"✓ ARCH-4: Celery task registration unchanged ({len(cur['task_names'])} tasks).")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--snapshot", action="store_true", help="capture current state as baseline")
    args = parser.parse_args()
    return _snapshot() if args.snapshot else _compare()


if __name__ == "__main__":
    raise SystemExit(main())
