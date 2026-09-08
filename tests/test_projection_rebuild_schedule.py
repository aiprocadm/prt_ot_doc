"""У каждого снимка есть тот, кто его пересобирает (BIZ-54-57 срез-128).

ЗАЧЕМ. Снимок (read model) — таблица, выведенная из других таблиц. Он врёт
молча: экран показывает СТАРЫЕ данные и выглядит рабочим. Проверить его
глазами нельзя — надо знать, что именно сейчас в исходных таблицах.

В этом репозитории такое случалось трижды подряд, и всегда одинаково:
пересборка НАПИСАНА, а позвать её некому. Срез-97 нашёл три проекции
аналитики, которые пересобирали только Celery-задачи, не стоявшие ни в одном
расписании. Срез-116 — снимок контрольных сроков, который ждал нажатия
кнопки. Срез-128 — поисковый снимок (общий поиск и CMD+K читают ТОЛЬКО его,
живого запроса у них нет) и снимок кабинета клиента, то есть ровно то
единственное, что видит заказчик.

ЧТО ПРОВЕРЯЕТСЯ. Список снимков берётся из кода — все таблицы модуля
проекций, а не из памяти. Для каждого прослеживается путь от строки ночного
расписания до вызова его пересборки: имя задачи → функция задачи → всё, что
она зовёт внутри своего модуля. У снимка ровно два законных состояния — его
пересобирают по расписанию либо причина названа здесь словами и ПРОВЕРЯЕТСЯ
отдельным тестом (кнопка в реестре причин ничего не стоит).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib

from app.db.session import TenantBase
from app.modules.projections import models as projection_models
from app.services.celery_app import celery_app

# Импорт регистрирует ночные задачи в Celery: без него расписание ссылается
# на имена, которых в реестре ещё нет.
import app.tasks._core  # noqa: F401  isort:skip

REPO = pathlib.Path(__file__).resolve().parents[1]

#: Снимок → чем он пересобирается. Значение — имена, которые должны
#: встретиться на пути от расписания: метод оркестратора или класс-сборщик.
#: Проверяется, что каждое имя в коде действительно есть (тест ниже), иначе
#: реестр протухнет молча — как протухла фраза «81 из 82» в срезе-124.
REBUILD_MARKS: dict[str, set[str]] = {
    "PackageReadModel": {"rebuild_package_projection", "PackageProjectionService"},
    "PersonComplianceReadModel": {
        "rebuild_person_projection",
        "rebuild_person_compliance_projection",
        "PersonComplianceProjectionService",
    },
    "SiteSafetyReadModel": {"rebuild_site_safety_projection", "SiteSafetyProjectionService"},
    "ContractorReadinessReadModel": {
        "rebuild_contractor_readiness_projection",
        "ContractorReadinessProjectionService",
    },
    "ClientPortalReadModel": {"rebuild_client_portal_projection", "ClientPortalProjectionService"},
    "SearchIndexEntry": {"rebuild_search_index"},
    "DashboardKpiSnapshot": {"rebuild_dashboard_snapshot"},
}

#: Таблицы модуля проекций, которые снимками НЕ являются: их строки заводит
#: человек или задача напрямую, выводить их не из чего. Названы поимённо, а не
#: отброшены по имени класса: «Job» и «Definition» — не признак, а привычка
#: называть, и первое же исключение из неё сделало бы сторожа слепым.
PRIMARY_TABLES: dict[str, str] = {
    "ExportJob": "заявка на выгрузку — её создаёт пользователь или задача отчётов",
    "ExportSchedule": "расписание выгрузок, заводится в центре экспорта",
    "KpiDefinition": "описание показателя, заводится пользователем",
    "PortalRequest": "обращение клиента из кабинета",
    "PortalRequestMessage": "сообщение в обращении клиента",
}

#: Снимки, которые НЕ пересобирают по расписанию осознанно. Причина обязана
#: объяснять, почему устаревание им не грозит.
NAMED_WITHOUT_SCHEDULE: dict[str, str] = {
    "DashboardKpiSnapshot": (
        "пересобирается ПРИ ЧТЕНИИ: сводка аналитики сама строит снимок за "
        "сегодня, если его ещё нет, — устареть он может максимум на один "
        "просмотр (проверяется тестом ниже)"
    ),
}


def _read_models() -> set[str]:
    """Снимки берём из кода: все таблицы модуля проекций."""

    found = set()
    for name in dir(projection_models):
        obj = getattr(projection_models, name)
        if isinstance(obj, type) and issubclass(obj, TenantBase) and hasattr(obj, "__tablename__"):
            if obj.__module__ == projection_models.__name__:
                found.add(name)
    return found


def _names_reachable_from(module_name: str, func_name: str) -> set[str]:
    """Все имена, до которых дотягивается задача внутри своего модуля.

    Задача устроена одинаково у всех тиков: обёртка `x_tick` зовёт корутину
    `_x_tick`, а та — сборщики. Поэтому обход идёт по вызовам функций того же
    модуля, пока они не кончатся.
    """

    module = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(module))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    seen: set[str] = set()
    names: set[str] = set()
    queue = [func_name]
    while queue:
        current = queue.pop()
        if current in seen or current not in functions:
            continue
        seen.add(current)
        for node in ast.walk(functions[current]):
            if isinstance(node, ast.Name):
                names.add(node.id)
                queue.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
    return names


def _scheduled_names() -> set[str]:
    """Что вообще пересобирается ночью — по расписанию, а не по памяти."""

    names: set[str] = set()
    for entry in celery_app.conf.beat_schedule.values():
        task = celery_app.tasks.get(entry["task"])
        run = getattr(task, "run", None)
        if run is None:
            continue
        names |= _names_reachable_from(run.__module__, run.__name__)
    return names


def test_список_снимков_берётся_из_кода() -> None:
    """Реестр без снимков — сломанный сторож."""

    models = _read_models()
    assert len(models) >= 6, f"снимки перестали находиться — сторож ослеп: {sorted(models)}"
    known = set(REBUILD_MARKS) | set(PRIMARY_TABLES)
    assert models == known, (
        "таблица модуля проекций не разобрана: каждая обязана быть либо снимком "
        "с пересборкой, либо названа первичной с причиной. "
        f"Новые {sorted(models - known)}, исчезли {sorted(known - models)}"
    )
    assert not (
        set(REBUILD_MARKS) & set(PRIMARY_TABLES)
    ), "таблица не может быть и снимком, и первичной"


def test_каждая_названная_пересборка_существует() -> None:
    """Имя сборщика, которого нет в коде, сделало бы сторожа зелёным впустую."""

    source = (REPO / "backend" / "app" / "modules" / "projections" / "services.py").read_text(
        encoding="utf-8"
    )
    missing = sorted(
        f"{model}:{mark}"
        for model, marks in REBUILD_MARKS.items()
        for mark in marks
        if mark not in source
    )
    assert missing == [], f"в коде нет таких сборщиков: {missing}"


def test_сторож_каждый_снимок_пересобирается_по_расписанию() -> None:
    """Написанная, но никем не позванная пересборка — это отсутствие пересборки.

    Целое ночное расписание — единственное место, где снимок обновляется сам;
    ручка и кнопка требуют человека, а данные устаревают без него.
    """

    scheduled = _scheduled_names()
    orphans = sorted(
        model
        for model, marks in REBUILD_MARKS.items()
        if model not in NAMED_WITHOUT_SCHEDULE and not (marks & scheduled)
    )
    assert orphans == [], (
        "снимок никто не пересобирает по расписанию — добавьте его в ночной тик "
        f"либо назовите причину в NAMED_WITHOUT_SCHEDULE: {orphans}"
    )


def test_сторож_названные_причины_не_протухают() -> None:
    """Снимок, который уже пересобирают ночью, в реестре причин не нужен."""

    scheduled = _scheduled_names()
    stale = sorted(
        model
        for model in NAMED_WITHOUT_SCHEDULE
        if model not in REBUILD_MARKS or (REBUILD_MARKS[model] & scheduled)
    )
    assert stale == [], f"реестр причин разошёлся с кодом: {stale}"


def test_снимок_сводки_действительно_собирается_при_чтении() -> None:
    """Причина «пересобирается при чтении» проверяется, а не принимается на слово."""

    source = (REPO / "backend" / "app" / "modules" / "analytics" / "api.py").read_text(
        encoding="utf-8"
    )
    assert "rebuild_dashboard_snapshot" in source, (
        "сводка аналитики больше не строит снимок при чтении — причина в "
        "NAMED_WITHOUT_SCHEDULE перестала быть верной"
    )
