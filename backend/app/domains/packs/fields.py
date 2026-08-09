"""BIZ-50 срез-4 (Доп. №1, разд. 50.2): что мастер обязан спросить.

Второй шаг мастера в ТЗ: «мастер спрашивает ТОЛЬКО то, чего не хватает
(объект, состав бригады, должности, даты)». Спросить только недостающее можно
лишь тогда, когда список полей сценария вообще существует как данные. До этого
среза он существовал ТОЛЬКО в виде вызовов ``data.get("...")`` внутри строителя
контекста: перечислить его не мог ни интерфейс, ни проверка готовности, ни
человек — приходилось читать код.

Что здесь объявлено:

* поля каждого сценария — что именно надо спросить у специалиста;
* обязательность — без чего документ выйдет бессмысленным, а не просто
  неполным;
* подписи на русском — общие для повторяющихся имён, чтобы «состав бригады»
  назывался одинаково во всех сценариях.

Три решения, которые важнее кода:

* **сведения о клиенте НЕ спрашиваются.** Организация, объект и сотрудник уже
  есть в карточке клиента (BIZ-49) — их подставляет конвейер. Спрашивать их
  второй раз и есть та «долгая настройка», от которой ТЗ уходит.
* **логотип и печать — не вопросы.** Это оформление с готовым умолчанием;
  показать их в списке вопросов значило бы утопить настоящие вопросы в шуме.
* **обязательность — про смысл документа, а не про заполненность.** «Стажировка»
  с умолчанием «не требуется» осмысленна пустой; «ФИО работника» — нет.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.packs.definitions import (
    PACK_CODE_CEO_SHIELD,
    PACK_CODE_CIVIL_DEFENCE,
    PACK_CODE_CONTRACTOR,
    PACK_CODE_FIRE_INSPECTION,
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_NEW_COMPANY,
    PACK_CODE_NEW_EMPLOYEE,
    PACK_CODE_OPO,
    PACK_CODE_SITE_ACCESS,
    PACK_CODE_WASTE,
)

__all__ = [
    "BRANDING_FIELDS",
    "FIELD_LABELS",
    "PackField",
    "SCENARIO_FIELDS",
    "expand_answers",
    "questions_for",
]

#: Оформление, а не вопросы: у обоих есть умолчание, и в списке вопросов они
#: только мешают.
BRANDING_FIELDS = frozenset({"logo", "stamp"})


@dataclass(frozen=True)
class PackField:
    """Один вопрос мастера."""

    name: str
    label: str
    #: ``True`` — без ответа документ выйдет бессмысленным, а не просто неполным.
    required: bool


#: Подписи общие: повторяющееся имя обязано звучать одинаково во всех
#: сценариях, иначе «состав бригады» и «участники» окажутся одним полем с
#: двумя названиями.
FIELD_LABELS: dict[str, str] = {
    # общие
    "hazards": "Опасные и вредные факторы",
    "work_types": "Виды работ",
    "ot_responsible": "Ответственный по охране труда",
    "pb_responsible": "Ответственный по пожарной безопасности",
    "team_members": "Состав бригады",
    "session_date": "Дата проведения",
    "notes": "Примечания",
    "supervisor": "Ответственный (подпись)",
    "position": "Должность",
    "person": "Инструктируемый",
    "instructor": "Инструктирующий",
    "entry_date": "Дата записи в журнале",
    "journal_title": "Название журнала",
    "journal_type": "Тип инструктажа",
    "issues": "Выданные СИЗ",
    "norms": "Нормы выдачи по должности",
    "ppe_officer": "Ответственный за выдачу СИЗ",
    "training_passed": "Обучение пройдено",
    "medical_clearance": "Медосмотр действителен",
    "ppe_ready": "СИЗ выданы",
    "drill_date": "Дата тренировки",
    "scenario": "Вводная обстановка",
    # новая компания
    "issued_at": "Дата издания",
    "ot_lead": "Руководитель по охране труда",
    "pb_lead": "Руководитель по пожарной безопасности",
    "policy_intro": "Преамбула политики",
    "employer_duties": "Обязанности работодателя",
    "employee_duties": "Обязанности работника",
    "journal_start": "Журнал: начат",
    "journal_end": "Журнал: окончен",
    "journal_notes": "Журнал: примечания",
    # несчастный случай
    "victim.name": "ФИО пострадавшего",
    "victim.position": "Должность пострадавшего",
    "incident_date": "Дата происшествия",
    "incident_location": "Место происшествия",
    "incident_description": "Обстоятельства",
    "incident_deadline": "Срок расследования",
    "commission": "Состав комиссии",
    "witnesses": "Очевидцы",
    "causes": "Причины",
    "actions": "Мероприятия",
    "follow_up": "Контроль исполнения",
    # подготовка к проверке
    "inspection_agency": "Надзорный орган",
    "inspection_date": "Дата проверки",
    "inspection_scope": "Предмет проверки",
    "inspection_lead": "Ответственный за взаимодействие",
    "inspection_contacts": "Контакты",
    "inspection_documents": "Запрошенные документы",
    "inspection_risks": "Риски и слабые места",
    "briefing_date": "Дата инструктажа персонала",
    "roles": "Роли на время проверки",
    "team": "Рабочая группа",
    # ОПО
    "opo_category": "Класс опасности объекта",
    "opo_process": "Технологический процесс",
    "opo_responsibles": "Ответственные лица",
    "opo_personnel": "Аттестованный персонал",
    "opo_courses": "Программы подготовки",
    "opo_permits": "Разрешения и лицензии",
    "opo_incidents": "Учёт инцидентов",
    "opo_alerts": "Оповещение",
    "opo_resources": "Силы и средства",
    "opo_contacts": "Контакты аварийных служб",
    # экология
    "waste_types": "Виды отходов",
    "waste_classes": "Классы опасности",
    "waste_storage": "Места накопления",
    "waste_removal": "Порядок вывоза",
    "waste_contractor": "Подрядчик по вывозу",
    "waste_contract_number": "Договор: номер",
    "waste_contract_validity": "Договор: срок действия",
    "waste_responsibles": "Ответственные за обращение с отходами",
    "waste_instructions": "Инструкции по обращению",
    "waste_control": "Производственный контроль",
    "personnel": "Персонал",
    # щит директора
    "ceo": "Генеральный директор",
    "deputy": "Заместитель",
    "delegation_scope": "Объём делегирования",
    "delegation_valid_until": "Срок действия делегирования",
    "eco_lead": "Ответственный по экологии",
    "reporting": "Порядок отчётности",
    "director_risks": "Риски руководителя",
    "contacts": "Контакты",
    # приём сотрудника
    "employee_name": "ФИО работника",
    "hire_date": "Дата приёма",
    "program": "Программа вводного инструктажа",
    "workplace": "Рабочее место",
    "instructions": "Инструкции по охране труда",
    "internship_days": "Стажировка (смен)",
    "medical_org": "Медицинская организация",
    "ppe_norms": "Нормы выдачи СИЗ",
    "sizes": "Размеры (одежда/обувь/СИЗОД)",
    "documents": "Документы для ознакомления",
    "employee_sign": "Подпись работника",
    # подрядчик
    "contractor_name": "Подрядная организация",
    "contractor_inn": "ИНН подрядчика",
    "contractor_responsible": "Ответственный от подрядчика",
    "headcount": "Численность персонала",
    "permits": "СРО и допуски",
    "training_status": "Обучение по охране труда",
    "medical_status": "Медосмотры персонала",
    "ppe_status": "Обеспеченность СИЗ",
    "permits_status": "Наряды-допуски",
    "insurance_status": "Страхование ответственности",
    "responsibility_split": "Разграничение зон ответственности",
    # пожарная проверка
    "extinguishers": "Первичные средства пожаротушения",
    "escape_routes": "Пути эвакуации и выходы",
    "alarm_systems": "Сигнализация и оповещение",
    "fire_doors": "Противопожарные преграды",
    "findings": "Замечания",
    "fire_works_rules": "Порядок огневых работ",
    "shutdown_rules": "Порядок обесточивания",
    "housekeeping": "Содержание территории и помещений",
    "fire_actions": "Действия при обнаружении пожара",
    "evacuation": "Порядок эвакуации",
    "drill_result": "Результат тренировки",
    "system_name": "Проверяемая система",
    "system_result": "Результат проверки системы",
    "next_check_date": "Дата следующей проверки",
    # ГО и ЧС
    "gochs_responsible": "Ответственный за гражданскую оборону",
    "threats": "Возможные чрезвычайные ситуации",
    "notification_order": "Порядок оповещения",
    "resources": "Силы и средства",
    "facility_category": "Категория объекта по ГО",
    "protection_storage": "Хранение средств защиты",
    "commission_head": "Председатель комиссии",
    "commission_members": "Члены комиссии",
    "commission_tasks": "Задачи комиссии",
    "lesson_topic": "Тема занятия",
}


def _fields(required: tuple[str, ...], optional: tuple[str, ...]) -> tuple[PackField, ...]:
    return tuple(
        PackField(name=name, label=FIELD_LABELS[name], required=is_required)
        for names, is_required in ((required, True), (optional, False))
        for name in names
    )


SCENARIO_FIELDS: dict[str, tuple[PackField, ...]] = {
    PACK_CODE_SITE_ACCESS: _fields(
        (
            "ot_responsible",
            "pb_responsible",
            "work_types",
            "hazards",
            "team_members",
            "session_date",
        ),
        (
            "position",
            "person",
            "instructor",
            "entry_date",
            "journal_title",
            "journal_type",
            "issues",
            "norms",
            "ppe_officer",
            "training_passed",
            "medical_clearance",
            "ppe_ready",
            "notes",
            "supervisor",
        ),
    ),
    PACK_CODE_NEW_COMPANY: _fields(
        ("issued_at", "ot_lead", "pb_lead"),
        (
            "policy_intro",
            "employer_duties",
            "employee_duties",
            "journal_start",
            "journal_end",
            "journal_notes",
        ),
    ),
    PACK_CODE_INCIDENT: _fields(
        (
            "victim.name",
            "victim.position",
            "incident_date",
            "incident_location",
            "incident_description",
            "commission",
        ),
        ("incident_deadline", "witnesses", "causes", "actions", "follow_up"),
    ),
    PACK_CODE_INSPECTION_PREP: _fields(
        ("inspection_agency", "inspection_date", "inspection_scope", "inspection_lead"),
        (
            "inspection_contacts",
            "inspection_documents",
            "inspection_risks",
            "briefing_date",
            "roles",
            "team",
            "actions",
        ),
    ),
    PACK_CODE_OPO: _fields(
        ("opo_category", "opo_process", "opo_responsibles", "hazards"),
        (
            "opo_personnel",
            "opo_courses",
            "opo_permits",
            "opo_incidents",
            "opo_alerts",
            "opo_resources",
            "opo_contacts",
        ),
    ),
    PACK_CODE_WASTE: _fields(
        ("waste_types", "waste_classes", "waste_responsibles"),
        (
            "waste_storage",
            "waste_removal",
            "waste_contractor",
            "waste_contract_number",
            "waste_contract_validity",
            "waste_instructions",
            "waste_control",
            "personnel",
        ),
    ),
    PACK_CODE_CEO_SHIELD: _fields(
        ("ceo", "delegation_scope", "ot_lead"),
        (
            "deputy",
            "delegation_valid_until",
            "pb_lead",
            "eco_lead",
            "reporting",
            "director_risks",
            "contacts",
        ),
    ),
    PACK_CODE_NEW_EMPLOYEE: _fields(
        ("employee_name", "position", "hire_date", "ot_responsible", "hazards"),
        (
            "program",
            "workplace",
            "instructions",
            "internship_days",
            "medical_org",
            "ppe_norms",
            "sizes",
            "documents",
            "employee_sign",
        ),
    ),
    PACK_CODE_CONTRACTOR: _fields(
        ("contractor_name", "contractor_inn", "work_types", "ot_responsible"),
        (
            "contractor_responsible",
            "headcount",
            "permits",
            "hazards",
            "training_status",
            "medical_status",
            "ppe_status",
            "permits_status",
            "insurance_status",
            "responsibility_split",
            "session_date",
            "team_members",
        ),
    ),
    PACK_CODE_FIRE_INSPECTION: _fields(
        ("pb_responsible", "extinguishers", "escape_routes", "alarm_systems", "fire_doors"),
        (
            "findings",
            "fire_works_rules",
            "shutdown_rules",
            "housekeeping",
            "fire_actions",
            "evacuation",
            "drill_date",
            "drill_result",
            "scenario",
            "team_members",
            "system_name",
            "system_result",
            "next_check_date",
        ),
    ),
    PACK_CODE_CIVIL_DEFENCE: _fields(
        ("gochs_responsible", "threats", "notification_order", "commission_head"),
        (
            "resources",
            "facility_category",
            "protection_storage",
            "commission_members",
            "commission_tasks",
            "scenario",
            "drill_date",
            "team_members",
            "lesson_topic",
            "session_date",
        ),
    ),
}


def expand_answers(answers: dict[str, object]) -> dict[str, object]:
    """Разложить ответы с точкой в имени во вложенные ключи payload.

    Строитель сценария «несчастный случай» читает пострадавшего вложенным
    объектом (``data["victim"]["name"]``), а мастеру нужны два отдельных
    вопроса. Имя с точкой описывает эту вложенность честно — вместо того чтобы
    заводить рядом плоское поле и держать в строителе две формы одного ответа.
    """

    result: dict[str, object] = {}
    for name, value in answers.items():
        head, _, tail = name.partition(".")
        if not tail:
            result[name] = value
            continue
        nested = result.setdefault(head, {})
        if isinstance(nested, dict):
            nested[tail] = value
    return result


def questions_for(pack_code: str) -> tuple[PackField, ...]:
    """Вопросы мастера по сценарию. Пустой кортеж — сценарий неизвестен."""

    return SCENARIO_FIELDS.get(pack_code, ())
