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
починены, четвёртая названа в реестре ниже.

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
import pathlib

import app.models  # noqa: F401  — регистрирует модели в реестре ORM
import app.modules.projections.models  # noqa: F401
from app.db.session import SharedBase, TenantBase

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Каталоги, где «упоминание модели» записью не является.
SKIP_PREFIXES = ("migrations/", "models/", "schemas/")

#: Таблицы без записи — с вердиктом. Вердикт обязан отвечать на вопрос
#: «почему это не дефект прямо сейчас» и, если дефект, — куда он записан.
WITHOUT_WRITERS: dict[str, str] = {
    # --- пусто и снаружи, и внутри: ни одного упоминания в backend/app ---
    "CorrectiveActionAttachment": "мёртвая: вложения корректирующих действий ведёт файловый контур",
    "IncidentAttachment": "мёртвая: вложения происшествия ведёт файловый контур",
    "InspectionAttachment": "мёртвая: вложения проверки ведёт файловый контур",
    "IncidentCase": "мёртвая с среза-117: живой контур происшествий — Incident",
    "IncidentInvestigation": "мёртвая с среза-117: расследование ведёт сам Incident",
    "InspectionChecklist": "мёртвая: чек-листы проверок ведёт контур safety_ops",
    "InspectionChecklistItem": "мёртвая: пункты чек-листа — см. InspectionChecklist",
    "InspectionPlan": "мёртвая: план проверок не заводит ни одна ручка",
    "InspectionPlanItem": "мёртвая: строки плана проверок — см. InspectionPlan",
    "InspectionRun": "мёртвая: прогон проверки не заводит ни одна ручка",
    "InspectionRunItem": "мёртвая: строки прогона проверки — см. InspectionRun",
    "OpsInspection": "мёртвая: живой контур проверок — Inspection",
    "PrescriptionItem": "мёртвая: строки предписания не заводит ни одна ручка",
    "InspectionPrepItem": (
        "читает GET /safety-ops (подготовка к проверке); строки не пишет никто — "
        "список пуст всегда"
    ),
    "PipelinePackageProfile": (
        "читает оркестратор конвейера при выборе профиля; профили пакетов не "
        "заводит ни одна ручка — ветка недостижима"
    ),
    # --- мёртвые: не пишет и не читает никто (кандидаты на удаление) ---
    "Asset": "мёртвая: ни записи, ни чтения; учёт имущества ведёт контур ОПО",
    "Equipment": "мёртвая: ни записи, ни чтения; средства ПБ живут в FireSafetyEquipment",
    "DocumentGenerationJob": "мёртвая: работу документов ведёт PipelineRun",
    "EdoReceipt": "мёртвая: квитанции ЭДО ведёт контур approval_runtime",
    "HazardBinding": "мёртвая: связи опасностей ведёт контур рисков (RiskAssessment)",
    "HazardMeasure": "мёртвая: меры ведёт контур рисков",
    "NpaClause": "мёртвая: пункты НПА не заводит ни одна ручка",
    "ReminderRule": "мёртвая с среза-114: правила напоминаний заменены тиками",
    "TenantRateLimit": "мёртвая: ограничение частоты живёт в настройках, а не в базе",
    "TrainingProtocolItem": "мёртвая: строки протокола обучения ведёт TrainingProtocol",
    # --- читают, но не пишет никто: экран показывает пустоту всегда ---
    "Risk": (
        "ПЕРЕДЕЛАТЬ (в Next): реестр рисков читает ещё GET /risk/risks через "
        "RiskService.list_by_site. Разрез аналитики, Командный центр и конструктор "
        "отчётов срез-131 перевёл на живые оценки; ручку — нет: её схема ответа "
        "жёстко держит шкалу 5×5 (probability/severity ge=1 le=5), а живая оценка "
        "считается методологией и такой шкалы не гарантирует. Это продуктовое решение"
    ),
    "RiskMeasure": "читает платформенная сводка и risk_enterprise; меры ведёт контур рисков",
    "Hazard": "читает платформенная сводка; справочник опасностей — RiskHazard",
    "NPA": "читает поисковый снимок; живой контур НПА — NpaAct/NpaRevision",
    "NPABinding": "читают разбор документов и оценка влияния НПА; связей никто не заводит",
    "NpaAct": "читает GET /npa; акты не заводит ни одна ручка — реестр пуст всегда",
    "NpaRevision": "читает оценка влияния НПА; редакции не заводит никто",
    "DocumentJobLog": "читает GET /jobs/{id}; строки журнала не пишет никто — журнал пуст",
    "PackRunLog": "читает таймлайн прогона пакета; строки не пишет никто — таймлайн пуст",
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


def _model_names() -> dict[str, str]:
    """Имя класса → имя таблицы. Список — из реестра ORM, а не из памяти."""

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
