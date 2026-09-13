"""Сторож: витрина не зовёт ручек, которых нет у сервера (срез-152).

ЗАЧЕМ. Сверка сопоставила ВСЕ вызовы `apiClient.*` с литеральным путём
(361 штука) с контрактом сервера — снимком OpenAPI
(`docs/stabilization/openapi_routes_baseline.json`, 1122 операции). Нашлись
вызовы в никуда, и один из них ломал основной сценарий:

* `POST /risk/assessments` — **кнопка «Сохранить расчёт» на экране рисков
  всегда кончалась 404**: сохранить оценку риска через интерфейс было нельзя
  вовсе. У сервера ручка называется `POST /risk/assess` и принимает другое
  тело (`items` с кодом опасности, `extra="forbid"`);
* `GET /risk/assessments/{id}/export` — выгрузки расчёта у сервера нет вовсе,
  кнопка «Скачать» давала 404.

Оба починены срезом-152. Остальные расхождения — в реестре ниже: у каждого
названа причина, и реестр обязан уменьшаться, а не расти.

КАК СВЕРЯЕТСЯ. Путь витрины приводится к виду с `{}` вместо подстановок
шаблона, путь сервера — к виду с `{}` вместо имён параметров; сравнение
посегментное, `{}` совпадает с любым одним сегментом. Так `/approvals/{}/{}`
законно сходится с `/approvals/{approval_id}/approve` (во фронте действие
подставляется переменной) и не даёт ложной тревоги.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "docs" / "stabilization" / "openapi_routes_baseline.json"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

#: Расхождения, которые дефектом НЕ являются: у каждого названа причина.
NOT_A_DEFECT: dict[str, str] = {
    "POST /analytics/ux-events": (
        "необязательная телеметрия интерфейса: ручки нет, витрина шлёт "
        "best-effort и глушит ошибку (`silentApiErrorToast`, комментарий в "
        "frontend/src/api/navigation.ts). Появится ручка — строка уйдёт"
    ),
    "GET /health/comprehensive": (
        "ручка существует (`backend/app/api/routes/health.py`), но её роутер "
        "объявлен с `include_in_schema=False` и потому не попадает в снимок "
        "OpenAPI — это граница контракта, а не дыра витрины"
    ),
    # Срез-153: `POST /packs` и `GET /packs/{id}` из реестра ушли — страница
    # комплектов и карточка компании ведут в мастер (`/packs/wizard` →
    # `POST /packs/run`), мёртвые функции хранилища удалены.
    "POST /files": (
        "`useFilesStore().upload` не вызывается ни одним экраном — мёртвая "
        "функция витрины (загрузка идёт через инициацию и multipart). "
        "Удаление хранилища файлов — отдельная уборка"
    ),
}

#: Расхождения, которые ЯВЛЯЮТСЯ дефектом и ждут своего среза. Здесь они
#: названы поимённо, чтобы не выглядеть нормой: реестр обязан пустеть.
DEFECTS_IN_QUEUE: dict[str, str] = {
    "POST /replace/dry-run": (
        "мастер документов зовёт СТАРЫЙ контракт замены (docx и карта замен "
        "одним запросом). Сервер принимает `POST /documents/"
        "{document_version_id}/replace:dry-run` по уже загруженной версии — "
        "перевод мастера это работа, а не правка пути"
    ),
    "GET /replace/reports/{}": (
        "та же пара: отчёт о замене сервер отдаёт как "
        "`GET /replace-runs/{replace_run_id}/report`"
    ),
}

KNOWN_GAPS: dict[str, str] = {**NOT_A_DEFECT, **DEFECTS_IN_QUEUE}

_CALL_RE = re.compile(
    r"apiClient\.(get|post|patch|put|delete)\s*(?:<[^>]*>)?\s*\(\s*(`[^`]*`|\"[^\"]*\"|'[^']*')",
    re.S,
)


def _server_paths() -> set[tuple[str, tuple[str, ...]]]:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    result: set[tuple[str, tuple[str, ...]]] = set()
    for operation in data["operations"]:
        method, _, path = operation.partition(" ")
        path = path.replace("/api/v1", "", 1)
        normalized = re.sub(r"\{[^}]+\}", "{}", path).rstrip("/") or "/"
        result.add((method.upper(), tuple(normalized.strip("/").split("/"))))
    return result


def _frontend_calls() -> dict[str, set[str]]:
    calls: dict[str, set[str]] = {}
    for path in list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx")):
        if ".test." in path.name or "__tests__" in path.parts:
            continue
        for match in _CALL_RE.finditer(path.read_text(encoding="utf-8")):
            raw = match.group(2)[1:-1]
            raw = re.sub(r"\$\{[^}]*\}", "{}", raw)
            if not raw.startswith("/"):
                continue
            url = raw.split("?")[0].rstrip("/") or "/"
            calls.setdefault(
                f"{match.group(1).upper()} {url}", set()
            ).add(str(path.relative_to(REPO_ROOT)))
    return calls


def _segment_matches(mine: str, theirs: str) -> bool:
    if mine == theirs or mine == "{}" or theirs == "{}":
        return True
    # Частичная подстановка внутри сегмента: `sign-{}` во фронте — это
    # `sign-employee`/`sign-instructor` на сервере (действие подставляется
    # переменной), поэтому сравниваем по образцу, а не буквально.
    if "{}" in mine:
        pattern = "^" + "[^/]+".join(re.escape(part) for part in mine.split("{}")) + "$"
        return re.match(pattern, theirs) is not None
    return False


def _matches(call_segments: tuple[str, ...], server_segments: tuple[str, ...]) -> bool:
    if len(call_segments) != len(server_segments):
        return False
    return all(
        _segment_matches(mine, theirs)
        for mine, theirs in zip(call_segments, server_segments)
    )


def _gaps() -> dict[str, set[str]]:
    server = _server_paths()
    gaps: dict[str, set[str]] = {}
    for call, files in _frontend_calls().items():
        method, _, url = call.partition(" ")
        segments = tuple(url.strip("/").split("/"))
        if any(
            server_method == method and _matches(segments, server_segments)
            for server_method, server_segments in server
        ):
            continue
        gaps[call] = files
    return gaps


def test_витрина_не_зовёт_несуществующих_ручек() -> None:
    calls = _frontend_calls()
    assert len(calls) > 100, f"вызовов найдено всего {len(calls)} — проверка потеряла область"

    unexpected = {call: files for call, files in _gaps().items() if call not in KNOWN_GAPS}
    assert not unexpected, "витрина зовёт ручки, которых нет в контракте сервера:\n" + "\n".join(
        f"  {call} — {', '.join(sorted(files))}" for call, files in sorted(unexpected.items())
    )


def test_реестр_известных_расхождений_не_протух() -> None:
    """Строка реестра, которая больше не нужна, обязана быть удалена: иначе
    список превращается в свалку и перестаёт что-либо означать."""

    gaps = set(_gaps())
    stale = sorted(set(KNOWN_GAPS) - gaps)
    assert not stale, f"расхождения больше нет — уберите их из KNOWN_GAPS: {stale}"


@pytest.mark.parametrize("call", sorted(KNOWN_GAPS))
def test_у_каждого_известного_расхождения_есть_причина(call: str) -> None:
    assert len(KNOWN_GAPS[call].strip()) > 30, f"{call}: причина должна быть объяснением"
