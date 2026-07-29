"""SEC-69 (разд. 69.1): вход для динамического скана (DAST).

ZAP обходит JSON-API по спецификации — обычный «паук» ходит по ссылкам в HTML,
которых у нас нет. Значит спецификация должна выгружаться надёжно, иначе скан
молча проверит пустоту и отчитается «чисто».

Спецификация берётся из объекта приложения, а не с живой ручки `/api/openapi.json`:
в production документация отключена намеренно, а ручка ещё и требует `X-Tenant` —
сканер не получил бы список эндпоинтов до аутентификации.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dast.yml"


def _load_dumper():
    path = REPO_ROOT / "scripts" / "ci" / "dump_openapi.py"
    spec = importlib.util.spec_from_file_location("dump_openapi", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_dump_produces_a_scannable_spec(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    assert _load_dumper().main(["--output", str(target)]) == 0

    spec = json.loads(target.read_text(encoding="utf-8"))
    paths = spec["paths"]
    # Пустая или куцая спецификация = скан «чисто» ни о чём. Порог с большим
    # запасом: на момент добавления путей ~680.
    assert len(paths) > 100, f"путей всего {len(paths)} — скан проверил бы почти ничего"
    assert any(p.startswith("/api/v1/") for p in paths)


def test_dump_fails_loudly_on_an_empty_spec(tmp_path: Path, monkeypatch) -> None:
    """Молчаливый успех на пустой спецификации — худший исход: отчёт «чисто»."""

    dumper = _load_dumper()

    class _EmptyApp:
        def openapi(self):
            return {"paths": {}}

    monkeypatch.setattr(dumper, "create_app", lambda: _EmptyApp(), raising=False)
    monkeypatch.setitem(
        __import__("sys").modules, "app.api.app", type("M", (), {"create_app": lambda: _EmptyApp()})
    )

    assert dumper.main(["--output", str(tmp_path / "x.json")]) == 1


@pytest.mark.parametrize("field", ["target", "format", "cmd_options"])
def test_workflow_feeds_zap_the_spec_and_a_live_target(field: str) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["zap-api-scan"]["steps"]
    zap = next(s for s in steps if str(s.get("uses", "")).startswith("zaproxy/"))

    assert field in zap["with"], f"шаг ZAP без параметра {field}"
    if field == "format":
        assert zap["with"]["format"] == "openapi"
    if field == "cmd_options":
        # -O задаёт живой хост: спецификация из файла, запросы — в приложение.
        assert "-O http://127.0.0.1:8000" in zap["with"]["cmd_options"]
        # Без заголовка тенанта каждый запрос отбивается middleware, и скан
        # проверил бы только обработчик ошибки.
        assert "X-Tenant" in zap["with"]["cmd_options"]


def test_workflow_does_not_run_on_every_pull_request() -> None:
    """Скан обходит 900+ операций; на каждом PR это минуты без новой информации."""

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert "pull_request" not in triggers
    assert "schedule" in triggers and "workflow_dispatch" in triggers


def test_workflow_starts_the_app_and_waits_for_health() -> None:
    """Скан по спецификации без живого приложения даёт отчёт об ошибках связи."""

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["zap-api-scan"]["steps"]
    start = next(s for s in steps if "Start backend" in str(s.get("name", "")))
    assert "/health" in start["run"], "старт без ожидания готовности — гонка"


def test_zap_rules_file_exists_and_is_documented() -> None:
    rules = REPO_ROOT / ".zap" / "rules.tsv"
    assert rules.exists()
    body = rules.read_text(encoding="utf-8")
    # Подавления без объяснения превращаются в «почему тут молчит?» через полгода.
    for line in body.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        assert len(parts) >= 3, f"правило без комментария: {line!r}"
