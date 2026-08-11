"""BIZ-61 срез-1 (Доп. №2, разд. 61.1): реестр модулей платформы.

ТЗ описывает модуль восемью атрибутами: код, название, категория, зависимости,
признак ядра, редакции, экраны фронтенда, права. В коде существовал ровно один
из них — название: ``FEATURE_CATALOG`` был плоским отображением «код → строка».

Чем это мешало на практике:

* **категория.** Админ-консоль и коммерческое предложение перечисляли девять
  модулей вперемешку: медосмотры рядом с конструктором отчётов. По какой
  дисциплине продаётся модуль, знал только тот, кто писал список.
* **признак ядра.** «Нельзя выключить» нигде не записано, поэтому вопрос «а
  этот модуль можно отключить заказчику?» решался чтением роутеров.
* **экраны фронтенда.** Разд. 61.3 требует прятать навигацию выключенного
  модуля. Прятать было нечего: связи «модуль → маршрут» не существовало, и
  фронт вынужден был знать её у себя — то есть повторять её второй раз.

Три решения, которые важнее кода:

* **набор ПРОДАВАЕМЫХ модулей не тронут.** ``FEATURE_CATALOG`` выводится из
  реестра и содержит ровно те же девять кодов: он участвует в сопоставлении
  тарифов (``plan_code_for_features``) и в гейтах роутеров, и молча добавить
  туда строку значило бы сдвинуть тариф у существующих арендаторов.
* **модули ядра объявлены, но НЕ продаются.** Они нужны, чтобы на вопрос
  «что нельзя выключить» отвечал реестр, а не память разработчика; в каталог
  и в тарифы они не попадают по построению.
* **зависимостей нет — и это записано явно.** Пустой ``depends_on`` у всех
  модулей не случайность: ратчет-гард ``scripts/ci/check_module_gates.py``
  падает, если зависимость появится, потому что «включение зависимости
  открывает больше, чем ожидалось» — риск из разд. 63.3, и решаться он должен
  осознанно, а не наследоваться молчанием.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "CORE_MODULES",
    "MODULE_REGISTRY",
    "ModuleDescriptor",
    "SELLABLE_MODULES",
    "module_titles",
    "modules_by_category",
]


@dataclass(frozen=True)
class ModuleDescriptor:
    """Модуль платформы по разд. 61.1."""

    code: str
    title: str
    #: Дисциплина или группа: по ней модуль ищут в консоли и в предложении.
    category: str
    #: ``True`` — ядро, выключить нельзя; в тарифы и каталог не входит.
    is_core: bool = False
    #: Коды модулей, без которых этот не работает. Пусто у всех намеренно —
    #: см. заголовок модуля.
    depends_on: tuple[str, ...] = ()
    #: Маршруты фронтенда, которые принадлежат модулю (разд. 61.3: скрыть
    #: навигацию выключенного модуля). Префиксы, а не точные пути: вложенные
    #: экраны появляются и исчезают чаще, чем меняется владелец раздела.
    ui_routes: tuple[str, ...] = ()
    #: Права RBAC модуля — связка с ролями (разд. 61.1).
    permissions: tuple[str, ...] = field(default_factory=tuple)


#: Ядро: перечислено, чтобы «нельзя выключить» было записано, а не подразумевалось.
CORE_MODULES: tuple[ModuleDescriptor, ...] = (
    ModuleDescriptor(
        code="tenancy",
        title="Арендаторы и доступ",
        category="Ядро",
        is_core=True,
        ui_routes=("/settings", "/users"),
    ),
    ModuleDescriptor(
        code="documents",
        title="Документы и шаблоны",
        category="Ядро",
        is_core=True,
        ui_routes=("/documents", "/templates", "/packs"),
    ),
    ModuleDescriptor(
        code="audit",
        title="Аудит и журналы",
        category="Ядро",
        is_core=True,
        ui_routes=("/audit",),
    ),
    ModuleDescriptor(
        code="employees",
        title="Сотрудники и оргструктура",
        category="Ядро",
        is_core=True,
        ui_routes=("/persons", "/companies", "/org-structure"),
    ),
    ModuleDescriptor(
        # Решение владельца (2026-08-08): импорт — ядро, а не товар. Загрузить
        # свои данные пачкой — первый шаг новичка; без него платформой не
        # начать пользоваться, и продавать вход бессмысленно.
        #
        # До этого решения модуль был недоступен ВООБЩЕ: гейт требовал строку
        # о выдаче с кодом ``imports``, а создать её в бою было нечем — кода
        # не было ни в каталоге, ни в одном тарифе. При этом пункт меню
        # «Импорт данных» видели владелец и админ любого арендатора и получали
        # «не найдено».
        code="imports",
        title="Импорт данных",
        category="Ядро",
        is_core=True,
        ui_routes=("/imports",),
        permissions=("imports.manage",),
    ),
)

#: Продаваемые модули. Порядок и состав кодов ЗАФИКСИРОВАНЫ: из них выводится
#: ``FEATURE_CATALOG``, а он участвует в сопоставлении тарифов.
SELLABLE_MODULES: tuple[ModuleDescriptor, ...] = (
    ModuleDescriptor(
        code="managed_clients",
        title="Ведение клиентов (аутсорсинг)",
        category="Документооборот",
        ui_routes=("/managed-clients",),
        permissions=("managed_clients.view",),
    ),
    ModuleDescriptor(
        code="committees",
        title="Комитеты",
        category="Охрана труда",
        ui_routes=("/committees",),
    ),
    ModuleDescriptor(
        code="contractors",
        title="Подрядчики",
        category="Охрана труда",
        ui_routes=("/contractors",),
    ),
    ModuleDescriptor(
        code="medical",
        title="Медосмотры",
        category="Охрана труда",
        ui_routes=("/medical",),
    ),
    ModuleDescriptor(
        code="report_builder",
        title="Конструктор отчётов",
        category="Аналитика",
        ui_routes=("/reports",),
    ),
    ModuleDescriptor(
        code="budget",
        title="Бюджет безопасности",
        category="Аналитика",
        ui_routes=("/budget",),
    ),
    ModuleDescriptor(
        code="sout",
        title="СОУТ",
        category="Охрана труда",
        ui_routes=("/sout",),
    ),
    ModuleDescriptor(
        code="rules_engine",
        title="Правила автоматизации",
        category="Ядро+",
        ui_routes=("/rules",),
    ),
    ModuleDescriptor(
        code="warehouse",
        title="Склад СИЗ",
        category="СИЗ",
        ui_routes=("/warehouse",),
    ),
)

MODULE_REGISTRY: tuple[ModuleDescriptor, ...] = CORE_MODULES + SELLABLE_MODULES


def module_titles() -> dict[str, str]:
    """``код → название`` только по ПРОДАВАЕМЫМ модулям.

    Это и есть исторический ``FEATURE_CATALOG``: гейты роутеров и сопоставление
    тарифов работают ровно по этому набору.
    """

    return {module.code: module.title for module in SELLABLE_MODULES}


def modules_by_category() -> dict[str, tuple[ModuleDescriptor, ...]]:
    """Модули, сгруппированные по дисциплине — для консоли и предложения."""

    grouped: dict[str, list[ModuleDescriptor]] = {}
    for module in MODULE_REGISTRY:
        grouped.setdefault(module.category, []).append(module)
    return {category: tuple(items) for category, items in sorted(grouped.items())}
