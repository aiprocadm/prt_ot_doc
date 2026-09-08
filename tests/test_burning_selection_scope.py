"""«Что горит» считается по одному правилу — опись отборов просрочки (BIZ-54-57 срез-127).

ЗАЧЕМ. Срез-89 завёл одну формулу «уволенный не в счёт»
(``services/person_scope``) и сторожа ``test_employed_person_formula`` — но
тот сторож ловит только СВОЮ КОПИЮ формулы. Написать условие заново нельзя, а
НЕ НАПИСАТЬ его вовсе — можно: пропуск не похож ни на что, ловить нечего.
Так и вышло. Срез-96 применил правило к виджетам аналитики, а те же счётчики
на сводке, в KPI, в сроках соответствия, у истекающих СИЗ и удостоверений и у
трёх правил качества данных остались без него: платформа отвечала на один и
тот же вопрос «что горит» разными числами, смотря какой экран открыть.

ЧТО ПРОВЕРЯЕТСЯ. Опись строится по коду, а не по памяти: разбор исходников
находит КАЖДОЕ место, где просрочка отбирается запросом (сравнение срока у
таблицы с ``person_id``, либо вызов общей формулы просрочки). У каждого
найденного места ровно два законных состояния — оно применяет правило либо
названо здесь поимённо с причиной. Список ломается в ОБЕ стороны: новое место
без правила и без причины — красный; названная причина, которой в коде больше
нет, — тоже красный, иначе реестр превращается в кладбище неверных строк
(тот же приём, что у полноты приёмки экранов в срезе-124).

ЧЕГО СТОРОЖ НЕ ВИДИТ. Просрочку, которую считают НЕ запросом, а разбором уже
загруженных строк в Python (подписи «просрочено» у аттестаций ОПО и мер
производственного контроля). Там нет отбора, который можно было бы прочитать
разбором, — эти места остаются на ревью человека.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Таблицы с ``person_id`` и сроком: сравнение такого срока в запросе и есть
#: отбор «что горит». Список закрыт намеренно — новая таблица со сроком по
#: человеку обязана попасть сюда осознанно, а не раствориться в шаблоне.
BURNING_COLUMNS: dict[str, set[str]] = {
    "Attestation": {"expires_at"},
    "BriefingEntry": {"valid_until"},
    "ComplianceDeadline": {"due_at"},
    "MedicalExam": {"valid_until"},
    "MedicalReferral": {"due_at"},
    "PPEIssue": {"expires_at"},
    "Permit": {"valid_until"},
    "Training": {"expires_at"},
    "TrainingCertificate": {"valid_until"},
    "TrainingEnrollment": {"due_at", "expires_at"},
    "TrainingPlan": {"due_date"},
}

#: Таблица, которая существует РАДИ сроков: снимок ``ComplianceDeadline``
#: не хранит ничего, кроме «что и когда истекает». Поэтому отбором «что горит»
#: считается любое чтение из неё, даже без сравнения даты, — иначе выборка
#: «весь снимок целиком, по возрастанию срока» (так была устроена ручка
#: `/compliance/deadlines`) не попадала бы в опись вовсе.
BURNING_TABLES = {"ComplianceDeadline"}

#: Готовые условия просрочки: кто их зовёт, тот отбирает просроченное — даже
#: если имени колонки у него в коде нет. Без этого места вроде счётчиков
#: рабочего места (они зовут ``overdue_compliance_deadline_where``) не попали
#: бы в опись вовсе.
BURNING_HELPERS = {
    "overdue_compliance_deadline_where",
    "pending_training_enrollment_where",
    "overdue_training_enrollment_where",
}

#: Признаки применённого правила. ``apply_person_scope`` из
#: ``api/helpers/client_scope`` сюда НЕ входит: имя похоже, смысл другой —
#: он сужает выборку до сотрудников ведомого клиента и про увольнение
#: не знает ничего.
FORMULA_MARKS = (
    "employed_record_where",
    "employed_person_where",
    "not_employed_record_where",
    "not_employed_person_ids",
    "_employed_only",
    "is_employed",
)

#: Места, где отбора по правилу НЕТ ОСОЗНАННО. Ключ — «путь::функция»,
#: значение — причина словами. Причина обязана объяснять, почему уволенный
#: здесь именно нужен; «так исторически» причиной не является.
NAMED_WITHOUT_RULE: dict[str, str] = {
    "api/routes/medical/exams.py::list_medical_exams": (
        "реестр медосмотров, а не сводка «что горит»: это журнал с фильтрами, "
        "и осмотр уволенного из истории пропадать не должен"
    ),
    "domains/permits/service.py::expire_due": (
        "служебное гашение статуса по времени: допуск уволенного тоже обязан "
        "перестать числиться действующим, иначе запись «действует» вечно"
    ),
    "modules/report_builder/datasets.py::_employees_training_stmt": (
        "набор строк для конструктора отчётов: отбор задаёт тот, кто строит "
        "отчёт, — тихий фильтр сделал бы отчёт «кого уволили с открытым "
        "обучением» невозможным"
    ),
    "services/calendar_aggregator.py::overdue_compliance_deadline_where": (
        "это САМА формула просрочки по времени; людей отбирает вызывающий"
    ),
    "services/discipline_training.py::overdue_training_enrollment_where": (
        "это САМА формула просрочки обучения; людей отбирает вызывающий"
    ),
    "services/discipline_numbers.py::collect_people_numbers": (
        "считает по УЖЕ переданному списку людей; список готовят площадка 360°, "
        "готовность клиента и карточка — каждый по общему правилу"
    ),
    "services/employee_card.py::_build_medicals": (
        "карточка ОДНОГО человека: у уволенного она светофор не считает вовсе "
        "(TERMINATED_REASON), а разделы показывает как историю"
    ),
    "services/employee_card.py::_build_ppe": ("карточка ОДНОГО человека — см. _build_medicals"),
    "services/employee_card.py::_build_permits": ("карточка ОДНОГО человека — см. _build_medicals"),
    "services/employee_card.py::_build_compliance_deadlines": (
        "карточка ОДНОГО человека — см. _build_medicals"
    ),
    "api/routes/pwa_sync.py::bootstrap": (
        "офлайн-набор ОДНОГО человека — того, кто вошёл; чужих сроков он "
        "не получает, а свои у уволенного и так недостижимы (входа нет)"
    ),
    "modules/compliance_deadlines/services.py::recompute_for_certificates": (
        "пересборка снимка: строки по уволенным в таблице ОСТАЮТСЯ намеренно "
        "(решение среза-93) — это история, невидимая при чтении; чистка "
        "потеряла бы её безвозвратно"
    ),
}


def _markers(node: ast.AST) -> set[str]:
    """Что в этой функции говорит «здесь отбирают просроченное»."""

    found: set[str] = set()
    for inner in ast.walk(node):
        # Сравнение срока: `MedicalExam.valid_until < today`. Сортировка
        # (`order_by(...desc())`) отбором не является — реестр, упорядоченный
        # по сроку, ничего не отбирает.
        if isinstance(inner, ast.Compare):
            for part in [inner.left, *inner.comparators]:
                if isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name):
                    columns = BURNING_COLUMNS.get(part.value.id)
                    if columns and part.attr in columns:
                        found.add(f"{part.value.id}.{part.attr}")
        if isinstance(inner, ast.Call) and isinstance(inner.func, (ast.Name, ast.Attribute)):
            name = inner.func.id if isinstance(inner.func, ast.Name) else inner.func.attr
            if name in BURNING_HELPERS:
                found.add(f"{name}()")
            # Чтение снимка сроков: `select(ComplianceDeadline)`,
            # `select_from(...)`, а также его пересборка.
            if name in {"select", "select_from", "delete", "update"}:
                for arg in inner.args:
                    if isinstance(arg, ast.Name) and arg.id in BURNING_TABLES:
                        found.add(f"{name}({arg.id})")
    return found


def _inventory() -> dict[str, tuple[bool, set[str]]]:
    """Опись по коду: «путь::функция» → (правило применено, чем опознано)."""

    found: dict[str, tuple[bool, set[str]]] = {}
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith(("migrations/", "models/", "schemas/")):
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            marks = _markers(node)
            if not marks:
                continue
            source = ast.get_source_segment(text, node) or ""
            has_rule = any(mark in source for mark in FORMULA_MARKS)
            found[f"{rel}::{node.name}"] = (has_rule, marks)
    return found


def test_опись_отборов_просрочки_не_пуста() -> None:
    """Сторож без находок — сломанный сторож.

    Если разбор перестанет узнавать запросы (переехали имена моделей, сменился
    стиль), опись опустеет, и все проверки ниже станут зелёными молча.
    """

    inventory = _inventory()
    assert len(inventory) >= 30, f"опись подозрительно мала — сторож ослеп: {len(inventory)}"


def test_сторож_каждый_отбор_что_горит_знает_про_увольнение() -> None:
    """Новое место без правила и без причины — красный.

    Пропуск правила ничем не выдаёт себя в коде: запрос выглядит обычно и
    работает. Заметен он только по расхождению чисел на двух экранах — то
    есть уже у пользователя.
    """

    offenders = sorted(
        name
        for name, (has_rule, _) in _inventory().items()
        if not has_rule and name not in NAMED_WITHOUT_RULE
    )
    assert offenders == [], (
        "отбор «что горит» не применяет правило «уволенный не в счёт» — "
        "возьмите employed_record_where из services/person_scope либо назовите "
        f"причину в NAMED_WITHOUT_RULE: {offenders}"
    )


def test_сторож_названные_причины_не_протухают() -> None:
    """Причина, которой в коде больше нет, — тоже красный.

    Иначе реестр копит строки про давно исправленные или переименованные
    места, и по нему уже нельзя ответить на вопрос «где правила нет».
    """

    inventory = _inventory()
    stale: list[str] = []
    for name in sorted(NAMED_WITHOUT_RULE):
        entry = inventory.get(name)
        if entry is None:
            stale.append(f"{name} — такой функции с отбором просрочки больше нет")
        elif entry[0]:
            stale.append(f"{name} — правило теперь применяется, причина не нужна")
    assert stale == [], f"реестр причин разошёлся с кодом: {stale}"


def test_у_каждой_причины_есть_объяснение() -> None:
    """Причина словами, а не отметка: пустая строка вернула бы молчаливый пропуск."""

    short = sorted(name for name, why in NAMED_WITHOUT_RULE.items() if len(why.strip()) < 40)
    assert short == [], f"причина не объясняет, почему уволенный здесь нужен: {short}"
