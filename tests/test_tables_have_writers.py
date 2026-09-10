"""У каждой таблицы есть тот, кто в неё пишет (BIZ-54-57 срез-131).

ЗАЧЕМ. Таблица, в которую никто не пишет, не выглядит поломкой: экран по ней
показывает ноль или пустой список, а ноль читается как «всё в порядке» —
«рисков нет», «журнал пуст», «событий не было». Проверить глазами нельзя:
надо знать, что строк там не бывает В ПРИНЦИПЕ.

Так уже случалось: срез-74 нашёл «давление происшествий», посчитанное по
таблице ``incident_cases``, которую ни одна ручка не заполняет (слой удалён
срезом-117). Срез-131 нашёл то же у РИСКОВ: в базе две таблицы про риски —
живые оценки (``risk_assessments``) и реестр ``risk``, в который не пишет
никто. По мёртвому реестру считали разрез аналитики, сигнал Командного центра,
набор строк конструктора отчётов и ручка ``GET /risk/risks``. Первые три
починены срезом-131, четвёртая — срезом-132; реестр ``risk`` больше не читает
никто и он ждёт волны удаления.

ЧТО ПРОВЕРЯЕТСЯ. Список таблиц берётся из ORM, а не из памяти. У каждой ровно
два законных состояния: в неё где-то пишут в ``backend/app`` либо она названа
здесь с вердиктом. Список ломается в обе стороны: новая таблица без записи —
красный; названная таблица, в которую снова начали писать (или которой не
стало), — тоже красный.

ЧЕГО СТОРОЖ НЕ ВИДИТ. Запись сырым SQL (``text("INSERT ...")``) и запись из
миграций: первое в продукте не принято, второе — не точка входа, а разовая
правка данных.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import pkgutil

import app.models  # noqa: F401  — регистрирует модели в реестре ORM
from app.db.session import SharedBase, TenantBase

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Каталоги, где «упоминание модели» записью не является.
SKIP_PREFIXES = ("migrations/", "models/", "schemas/")

#: Таблицы без записи — с вердиктом. Вердикт обязан отвечать на вопрос
#: «почему это не дефект прямо сейчас» и, если дефект, — куда он записан.
WITHOUT_WRITERS: dict[str, str] = {
    # Срез-135: 24 модели с вердиктом «мёртвая» удалены из кода. Таблицы в
    # базе ОСТАЛИСЬ (список — в docs/CLEANUP_CANDIDATES.md): удалять данные
    # без владельца нельзя, а без модели они уже никому не видны.
    "PipelinePackageProfile": (
        "читает оркестратор конвейера при выборе профиля; профили пакетов не "
        "заводит ни одна ручка — ветка недостижима"
    ),
    # --- мёртвые: не пишет и не читает никто (кандидаты на удаление) ---
    # Срез-135: эти две нашлись только после того, как сторож стал загружать
    # ВСЕ модули с моделями. До этого они не попадали в реестр ORM вовсе —
    # то есть были невидимы даже описи.
    "Checklist": (
        "мёртвая: чек-листы проверок ведёт контур safety_ops (Finding), "
        "а эту таблицу не читает и не пишет ни одна ручка"
    ),
    "Violation": (
        "мёртвая: нарушения ведёт контур происшествий и предписаний; "
        "эту таблицу не читает и не пишет ни одна ручка"
    ),
    # --- читают, но не пишет никто: экран показывает пустоту всегда ---
    # (срез-133 убрал отсюда журнал задания и таймлайн прогона пакета —
    # в обе таблицы теперь пишет тот, кто эти события и производит)
    # Срез-138 вернул сюда DocumentGenerationJob (её читали ручки документов —
    # вердикт «мёртвая» был неверен); срез-139 снял чтение и удалил модель:
    # состояния «генерируется» у документа не бывает, ветки не срабатывали никогда.
    "RiskMeasure": "читает платформенная сводка и risk_enterprise; меры ведёт контур рисков",
    "Hazard": "читает платформенная сводка; справочник опасностей — RiskHazard",
    # (срез-142 убрал отсюда NPA и NPABinding: модель NPA удалена, связи заводит
    # POST /npa/{id}/bindings — и оценка влияния наконец считает по ним)
    # (срез-141 убрал отсюда NpaAct/NpaClause/NpaRevision — реестр актов
    # заводит владелец платформы через POST /npa и POST /npa/{id}/revisions)
    "BillingPlan": "читают биллинг и GET /billing; тарифы заводятся вне продукта",
    "BillingInvoice": "читает биллинг; счета выставляются вне продукта",
    "TenantLimitOverride": "читает биллинг; исключения по лимитам заводятся вне продукта",
    "TenantIntegrationKey": "читают биллинг и готовность интеграций; ключи заводятся вне продукта",
    # --- пишут только тесты ---
    "WebhookSubscription": (
        "пишут только тесты: живые подписки — WebhookEndpoint с полным CRUD; "
        "рассылка проверяет эту таблицу первой и на PostgreSQL не видит её строк "
        "(SEC-65), ветка оставлена ради совместимости с SQLite — см. services/webhooks"
    ),
}


def _import_all_model_modules() -> None:
    """Загрузить ВСЕ модули с моделями — иначе опись зависит от случая.

    Срез-135: реестр ORM наполняется по мере импорта. Пока сторож полагался на
    то, что успело импортироваться, его итог зависел от СОСТАВА прогона: в
    одиночку он видел 238 моделей, а рядом с тестами, поднимающими приложение,
    — 248, и две таблицы (``checks``, ``violations``) появлялись в сиротах
    только во втором случае. Сторож, отвечающий по-разному на один и тот же
    вопрос, не сторож.
    """

    packages = [app.models]
    try:
        import app.modules as modules_pkg

        packages.append(modules_pkg)
    except ImportError:  # pragma: no cover — модуль есть всегда
        pass
    for package in packages:
        for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            if module.name.endswith(("models", "model")) or ".models." in module.name:
                importlib.import_module(module.name)


def _model_names() -> dict[str, str]:
    """Имя класса → имя таблицы. Список — из реестра ORM, а не из памяти."""

    _import_all_model_modules()
    found: dict[str, str] = {}
    for base in (TenantBase, SharedBase):
        for mapper in base.registry.mappers:
            cls = mapper.class_
            found[cls.__name__] = cls.__tablename__
    return found


def _written_names() -> set[str]:
    """Имена, которые где-то в ``backend/app`` используются для ЗАПИСИ."""

    written: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith(SKIP_PREFIXES):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — синтаксис ловит сам pytest
            continue
        for node in ast.walk(tree):
            # `Model(...)` — создание строки.
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                written.add(node.func.id)
                # `insert(Model)`, `update(Model)`, `delete(Model)`, `add(Model(...))`
                if node.func.id in {"insert", "update", "delete", "bulk_insert_mappings"}:
                    for arg in node.args:
                        if isinstance(arg, ast.Name):
                            written.add(arg.id)
            # `Model.__table__.insert()` и подобное.
            if isinstance(node, ast.Attribute) and node.attr == "__table__":
                if isinstance(node.value, ast.Name):
                    written.add(node.value.id)
    return written


def _orphans() -> set[str]:
    return set(_model_names()) - _written_names()


def test_список_таблиц_берётся_из_orm() -> None:
    """Сторож без таблиц — сломанный сторож."""

    models = _model_names()
    assert len(models) > 200, f"таблицы перестали находиться: {len(models)}"


def test_сторож_у_каждой_таблицы_есть_тот_кто_в_неё_пишет() -> None:
    """Ноль строк читается как «всё в порядке» — и потому не выглядит поломкой."""

    unnamed = sorted(_orphans() - set(WITHOUT_WRITERS))
    assert unnamed == [], (
        "в таблицу не пишет никто в backend/app — заведите точку входа либо "
        f"назовите вердикт в WITHOUT_WRITERS: {unnamed}"
    )


def test_сторож_реестр_вердиктов_не_протухает() -> None:
    """Таблица, в которую снова пишут (или которой не стало), из реестра уходит."""

    orphans = _orphans()
    models = set(_model_names())
    stale = sorted(
        name
        for name in WITHOUT_WRITERS
        if name not in orphans or (name not in models and name not in orphans)
    )
    assert stale == [], f"реестр вердиктов разошёлся с кодом: {stale}"


def test_у_каждого_вердикта_есть_объяснение() -> None:
    """Отметка без слов не отличает «мёртвая» от «сломанная»."""

    short = sorted(name for name, why in WITHOUT_WRITERS.items() if len(why.strip()) < 30)
    assert short == [], f"вердикт ничего не объясняет: {short}"


def _dead_table_names() -> set[str]:
    """Таблицы с вердиктом «мёртвая»: их не пишет и не читает ни один экран."""

    return {name for name, why in WITHOUT_WRITERS.items() if why.lstrip().startswith("мёртвая")}


#: Тесты, которые заводят строки МЁРТВОЙ таблицы осознанно. Пусто: такой тест
#: проверяет собственную подготовку данных, а не продукт.
TESTS_SEEDING_DEAD_TABLES: dict[str, str] = {}


def test_сторож_тесты_не_засевают_мёртвые_таблицы() -> None:
    """Тест, который сам создаёт то, чего продукт не создаёт, — зелёный впустую.

    Срез-134: так вышло ЧЕТЫРЕЖДЫ подряд. Проверки разреза аналитики,
    Командного центра, конструктора отчётов и ручки рисков заводили строки
    реестра ``risk`` — таблицы, в которую продукт не пишет никогда. Все они
    были зелёными, пока экраны в бою показывали ноль; и они же покраснели,
    когда экраны наконец перевели на живые данные.

    Признак один: тест готовит данные тем способом, которым продукт их не
    создаёт. Тогда проверка держит собственную подготовку, а не поведение.
    """

    dead = _dead_table_names()
    offenders: list[str] = []
    for root in ("tests", "backend/tests", "integration_tests"):
        base = REPO / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel in TESTS_SEEDING_DEAD_TABLES:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            # Считаем только имена, ВЗЯТЫЕ ИЗ МОДЕЛЕЙ продукта: у тестов
            # бывают свои классы с теми же именами (`Violation` — помощник
            # проверки миграций), и по одному имени их не отличить.
            from_models: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                    from_models.update(alias.asname or alias.name for alias in node.names)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in dead and node.func.id in from_models:
                        offenders.append(f"{rel}:{node.lineno} {node.func.id}")
    assert offenders == [], (
        "тест заводит строки таблицы, в которую продукт не пишет никогда — "
        "сейте тем же способом, каким данные создаёт продукт: " + str(sorted(set(offenders)))
    )
