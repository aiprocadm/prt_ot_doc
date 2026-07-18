"""Default document pack catalogue shipped with the service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from typing import Callable, Sequence

from docx import Document

from app.models.models import DocumentPackModule, DocumentPackScenario
from app.modules.packs.assets import (
    DEFAULT_LOGO_BYTES,
    DEFAULT_STAMP_BYTES,
    build_inline_image_descriptor,
)

__all__ = [
    "PackTemplateSpec",
    "PackDefinition",
    "PackScenario",
    "DEFAULT_PACKS",
    "PACK_DEFINITIONS_BY_CODE",
    "PACK_CODE_SITE_ACCESS",
    "PACK_CODE_NEW_COMPANY",
    "PACK_CODE_INCIDENT",
    "PACK_CODE_INSPECTION_PREP",
    "PACK_CODE_OPO",
    "PACK_CODE_WASTE",
    "PACK_CODE_CEO_SHIELD",
]


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

PACK_CODE_SITE_ACCESS = "OT_ENTER_SITE"
PACK_CODE_NEW_COMPANY = "NEW_COMPANY"
PACK_CODE_INCIDENT = "INCIDENT_RESPONSE"
PACK_CODE_INSPECTION_PREP = "OT_INSPECTION_PREP"
PACK_CODE_OPO = "OPO_COMPLIANCE"
PACK_CODE_WASTE = "ECO_WASTE"
PACK_CODE_CEO_SHIELD = "CEO_SHIELD"


class PackScenario(str, Enum):
    ENTER_SITE = "enter_site"
    INCIDENT = "incident"
    INSPECTION_PREP = "inspection_preparation"
    OPO = "hazardous_production_facility"
    WASTE = "waste_and_ecology"
    CEO_SHIELD = "ceo_shield"
    NEW_COMPANY = "new_company"


@dataclass(slots=True, frozen=True)
class PackTemplateSpec:
    code: str
    name: str
    description: str
    category: str
    builder: Callable[[], bytes]


@dataclass(slots=True, frozen=True)
class PackDefinition:
    code: str
    name: str
    description: str
    scenario: PackScenario
    module: DocumentPackModule
    scenario_type: DocumentPackScenario
    templates: Sequence[PackTemplateSpec]
    item_order: Sequence[str]
    metadata: dict[str, str]


def _doc(*paragraphs: str, header: str | None = None, footer: str | None = None) -> bytes:
    doc = Document()
    section = doc.sections[0]
    if header:
        header_para = section.header.paragraphs[0]
        header_para.text = header
    if footer:
        footer_para = section.footer.paragraphs[0]
        footer_para.text = footer
    for text in paragraphs:
        doc.add_paragraph(text)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _site_access_order() -> bytes:
    return _doc(
        "Приказ на выход на объект",
        "Компания: {{ company.name }} (ИНН {{ company.inn }})",
        "Адрес объекта: {{ site.address }}",
        "Ответственный по охране труда: {{ ot_responsible }}",
        "Ответственный по пожарной безопасности: {{ pb_responsible }}",
        "Виды работ: {{ work_types }}",
        "Опасные факторы: {{ hazards }}",
        header="{{ logo }}",
        footer="{{ stamp }}",
    )


def _site_access_briefing() -> bytes:
    return _doc(
        "Инструктаж перед выходом на объект",
        "Дата: {{ data.session_date }}",
        "Состав бригады: {{ data.team_members }}",
        "Ответственный по охране труда: {{ ot_responsible }}",
        "Ответственный по пожарной безопасности: {{ pb_responsible }}",
        "Перечень опасностей: {{ hazards }}",
        footer="Контроль: {{ stamp }}",
    )


def _site_access_checklist() -> bytes:
    return _doc(
        "Чек-лист допуска",
        "1. Обучение пройдено: {{ data.training_passed }}",
        "2. Медосмотр действителен: {{ data.medical_clearance }}",
        "3. СИЗ выданы: {{ data.ppe_ready }}",
        "4. Дополнительные отметки: {{ data.notes }}",
        footer="Подпись ответственного: {{ data.supervisor }}",
    )


def _site_access_ppe_card() -> bytes:
    return _doc(
        "Личная карточка учета СИЗ",
        "Работник: {{ person.full_name }}",
        "Должность: {{ position.name }}",
        "Выданные СИЗ: {{ data.issues }}",
        "Нормы по должности: {{ data.norms }}",
        footer="Ответственный: {{ data.ppe_officer }}",
    )


def _site_access_journal_entry() -> bytes:
    return _doc(
        "Лист журнала инструктажей",
        "Журнал: {{ journal.title }}",
        "Тип: {{ journal.journal_type }}",
        "Дата: {{ data.entry_date }}",
        "Инструктируемый: {{ data.person }}",
        "Ответственный: {{ data.instructor }}",
        footer="Подпись ответственного: {{ data.instructor }}",
    )


def _new_company_order() -> bytes:
    return _doc(
        "Приказ о создании службы охраны труда",
        "Организация: {{ company.name }}",
        "ИНН: {{ company.inn }}",
        "Адрес: {{ company.address }}",
        "Дата: {{ data.issued_at }}",
        "Назначить ответственным: {{ data.ot_lead }}",
        footer="Подпись директора: {{ stamp }}",
    )


def _new_company_instruction() -> bytes:
    return _doc(
        "Инструкция по охране труда",
        "Раздел 1. Общие положения",
        "{{ data.policy_intro }}",
        "Раздел 2. Обязанности работодателя",
        "{{ data.employer_duties }}",
        "Раздел 3. Обязанности работников",
        "{{ data.employee_duties }}",
        header="{{ logo }}",
    )


def _new_company_journal() -> bytes:
    return _doc(
        "Журнал регистрации инструктажей",
        "Организация: {{ company.name }}",
        "Ответственный: {{ data.ot_lead }}",
        "Начат: {{ data.journal_start }}",
        "Завершён: {{ data.journal_end }}",
        "Примечания: {{ data.journal_notes }}",
    )


def _new_company_policy() -> bytes:
    return _doc(
        "Политика в области охраны труда и пожарной безопасности",
        "Организация: {{ company.name }}",
        "Политика утверждена: {{ data.issued_at }}",
        "Ответственный за исполнение: {{ data.pb_lead }}",
        footer="{{ stamp }}",
    )


def _incident_report() -> bytes:
    return _doc(
        "Акт о несчастном случае",
        "Дата происшествия: {{ incident.date }}",
        "Место: {{ incident.location }}",
        "Пострадавший: {{ victim.name }} ({{ victim.position }})",
        "Описание события: {{ incident.description }}",
        "Свидетели: {{ witnesses }}",
        "Причины: {{ causes }}",
        "Мероприятия: {{ actions }}",
        footer="Комиссия: {{ commission }}",
    )


def _incident_commission_order() -> bytes:
    return _doc(
        "Приказ о создании комиссии",
        "Организация: {{ company.name }}",
        "Дата: {{ incident.date }}",
        "Состав комиссии: {{ commission }}",
        "Срок расследования: {{ incident.deadline }}",
        footer="Подпись руководителя: {{ stamp }}",
    )


def _incident_plan() -> bytes:
    return _doc(
        "План корректирующих мероприятий",
        "Организация: {{ company.name }}",
        "Инцидент: {{ incident.description }}",
        "Причины: {{ causes }}",
        "Мероприятия: {{ actions }}",
        "Контроль исполнения: {{ data.follow_up }}",
        header="{{ logo }}",
    )


def _inspection_plan() -> bytes:
    return _doc(
        "План подготовки к проверке",
        "Надзорный орган: {{ inspection.agency }}",
        "Дата визита: {{ inspection.date }}",
        "Ответственный: {{ inspection.lead }}",
        "Перечень документов: {{ inspection.documents }}",
        footer="{{ stamp }}",
    )


def _inspection_checklist() -> bytes:
    return _doc(
        "Чек-лист готовности к проверке",
        "Область проверки: {{ inspection.scope }}",
        "Ключевые риски: {{ inspection.risks }}",
        "Контакты на месте: {{ inspection.contacts }}",
        footer="{{ logo }}",
    )


def _inspection_briefing() -> bytes:
    return _doc(
        "Инструктаж команды перед проверкой",
        "Дата инструктажа: {{ data.briefing_date }}",
        "Участники: {{ data.team }}",
        "Роли и обязанности: {{ data.roles }}",
        "Согласованные действия: {{ data.actions }}",
        footer="{{ stamp }}",
    )


def _opo_passport() -> bytes:
    return _doc(
        "Паспорт ОПО",
        "Категория опасности: {{ opo.category }}",
        "Технологический процесс: {{ opo.process }}",
        "Опасные факторы: {{ hazards }}",
        "Ответственные лица: {{ opo.responsibles }}",
        header="{{ logo }}",
    )


def _opo_emergency_plan() -> bytes:
    return _doc(
        "План ликвидации аварий",
        "Контакты аварийных служб: {{ opo.contacts }}",
        "Сценарии аварий: {{ opo.incidents }}",
        "Ресурсы и средства: {{ opo.resources }}",
        "Порядок оповещения: {{ opo.alerts }}",
        footer="{{ stamp }}",
    )


def _opo_training_matrix() -> bytes:
    return _doc(
        "Матрица обучения ОПО",
        "Персонал: {{ opo.personnel }}",
        "Требуемые курсы: {{ opo.courses }}",
        "Допуски и удостоверения: {{ opo.permits }}",
        footer="{{ logo }}",
    )


def _waste_register() -> bytes:
    return _doc(
        "Реестр отходов",
        "Типы отходов: {{ waste.types }}",
        "Классы опасности: {{ waste.classes }}",
        "Места накопления: {{ waste.storage }}",
        "Учёт и вывоз: {{ waste.removal }}",
        header="{{ logo }}",
    )


def _waste_contract() -> bytes:
    return _doc(
        "Договор на обращение с отходами",
        "Подрядчик: {{ waste.contractor }}",
        "Номер договора: {{ waste.contract_number }}",
        "Срок действия: {{ waste.contract_validity }}",
        "Ответственные: {{ waste.responsibles }}",
        footer="{{ stamp }}",
    )


def _waste_briefing() -> bytes:
    return _doc(
        "Памятка по обращению с отходами",
        "Персонал: {{ data.personnel }}",
        "Инструкции: {{ waste.instructions }}",
        "Контроль: {{ waste.control }}",
        footer="{{ logo }}",
    )


def _ceo_order() -> bytes:
    return _doc(
        "Приказ генерального директора",
        "Организация: {{ company.name }}",
        "Назначить ответственным по ОТ: {{ shield.ot_lead }}",
        "Назначить ответственным по ПБ: {{ shield.pb_lead }}",
        "Назначить ответственным по экологии: {{ shield.eco_lead }}",
        footer="{{ stamp }}",
    )


def _ceo_delegation() -> bytes:
    return _doc(
        "Делегирование полномочий",
        "Директор: {{ shield.ceo }}",
        "Заместитель: {{ shield.deputy }}",
        "Объём полномочий: {{ shield.scope }}",
        "Срок действия: {{ shield.valid_until }}",
        header="{{ logo }}",
    )


def _ceo_control_card() -> bytes:
    return _doc(
        "Карта контроля директора",
        "Ключевые риски: {{ shield.risks }}",
        "Отчётность: {{ shield.reporting }}",
        "Каналы связи: {{ shield.contacts }}",
        footer="{{ stamp }}",
    )


DEFAULT_PACKS: Sequence[PackDefinition] = (
    PackDefinition(
        code=PACK_CODE_SITE_ACCESS,
        name="Выход на объект",
        description="Комплект документов для допуска бригады на объект",
        scenario=PackScenario.ENTER_SITE,
        module=DocumentPackModule.OT,
        scenario_type=DocumentPackScenario.DOCUMENT_BATCH,
        templates=(
            PackTemplateSpec(
                code="pack_ot_site_order",
                name="Приказ на выход",
                description="Распоряжение о выходе на объект",
                category="order",
                builder=_site_access_order,
            ),
            PackTemplateSpec(
                code="pack_ot_site_briefing",
                name="Инструктаж перед выходом",
                description="Протокол вводного инструктажа",
                category="instruction",
                builder=_site_access_briefing,
            ),
            PackTemplateSpec(
                code="pack_ot_site_ppe_card",
                name="Карточка СИЗ",
                description="Личная карточка выдачи СИЗ",
                category="ppe_card",
                builder=_site_access_ppe_card,
            ),
            PackTemplateSpec(
                code="pack_ot_site_journal",
                name="Журнал инструктажей",
                description="Лист регистрации инструктажа",
                category="journal",
                builder=_site_access_journal_entry,
            ),
            PackTemplateSpec(
                code="pack_ot_site_checklist",
                name="Чек-лист допуска",
                description="Контроль требований перед выходом",
                category="checklist",
                builder=_site_access_checklist,
            ),
        ),
        item_order=(
            "pack_ot_site_order",
            "pack_ot_site_briefing",
            "pack_ot_site_ppe_card",
            "pack_ot_site_journal",
            "pack_ot_site_checklist",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
        },
    ),
    PackDefinition(
        code=PACK_CODE_NEW_COMPANY,
        name="Новая компания",
        description="Стартовый комплект документов по охране труда и пожарной безопасности",
        scenario=PackScenario.NEW_COMPANY,
        module=DocumentPackModule.OT,
        scenario_type=DocumentPackScenario.DOCUMENT_BATCH,
        templates=(
            PackTemplateSpec(
                code="pack_new_company_order",
                name="Приказ",
                description="Приказ о создании службы ОТ",
                category="order",
                builder=_new_company_order,
            ),
            PackTemplateSpec(
                code="pack_new_company_instruction",
                name="Инструкция",
                description="Базовая инструкция по охране труда",
                category="instruction",
                builder=_new_company_instruction,
            ),
            PackTemplateSpec(
                code="pack_new_company_journal",
                name="Журнал",
                description="Журнал регистрации инструктажей",
                category="journal",
                builder=_new_company_journal,
            ),
            PackTemplateSpec(
                code="pack_new_company_policy",
                name="Политика",
                description="Политика в области ОТ/ПБ",
                category="policy",
                builder=_new_company_policy,
            ),
        ),
        item_order=(
            "pack_new_company_order",
            "pack_new_company_instruction",
            "pack_new_company_journal",
            "pack_new_company_policy",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
        },
    ),
    PackDefinition(
        code=PACK_CODE_INCIDENT,
        name="Несчастный случай",
        description="Документы для расследования несчастного случая",
        scenario=PackScenario.INCIDENT,
        module=DocumentPackModule.OT,
        scenario_type=DocumentPackScenario.WORKFLOW,
        templates=(
            PackTemplateSpec(
                code="pack_incident_report",
                name="Акт",
                description="Акт о несчастном случае",
                category="report",
                builder=_incident_report,
            ),
            PackTemplateSpec(
                code="pack_incident_commission",
                name="Приказ",
                description="Приказ о создании комиссии",
                category="order",
                builder=_incident_commission_order,
            ),
            PackTemplateSpec(
                code="pack_incident_plan",
                name="План мероприятий",
                description="Перечень корректирующих действий",
                category="plan",
                builder=_incident_plan,
            ),
        ),
        item_order=(
            "pack_incident_report",
            "pack_incident_commission",
            "pack_incident_plan",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
            "entity": "incident",
            "models": "Incident,IncidentLog",
            "context_keys": "incident_id,company_id,site_id,victim_ids",
        },
    ),
    PackDefinition(
        code=PACK_CODE_INSPECTION_PREP,
        name="Подготовка к проверке",
        description="Комплект для подготовки к проверке ГИТ/МЧС/Ростехнадзора",
        scenario=PackScenario.INSPECTION_PREP,
        module=DocumentPackModule.OT,
        scenario_type=DocumentPackScenario.WORKFLOW,
        templates=(
            PackTemplateSpec(
                code="pack_inspection_plan",
                name="План",
                description="План подготовки к визиту",
                category="plan",
                builder=_inspection_plan,
            ),
            PackTemplateSpec(
                code="pack_inspection_checklist",
                name="Чек-лист",
                description="Чек-лист готовности к проверке",
                category="checklist",
                builder=_inspection_checklist,
            ),
            PackTemplateSpec(
                code="pack_inspection_briefing",
                name="Инструктаж",
                description="Инструктаж команды перед проверкой",
                category="instruction",
                builder=_inspection_briefing,
            ),
        ),
        item_order=(
            "pack_inspection_plan",
            "pack_inspection_checklist",
            "pack_inspection_briefing",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
            "entity": "inspection",
            "context_keys": "inspection_id,company_id,site_id",
        },
    ),
    PackDefinition(
        code=PACK_CODE_OPO,
        name="ОПО",
        description="Документы для опасных производственных объектов",
        scenario=PackScenario.OPO,
        module=DocumentPackModule.OT,
        scenario_type=DocumentPackScenario.DOCUMENT_BATCH,
        templates=(
            PackTemplateSpec(
                code="pack_opo_passport",
                name="Паспорт",
                description="Паспорт опасного объекта",
                category="passport",
                builder=_opo_passport,
            ),
            PackTemplateSpec(
                code="pack_opo_emergency_plan",
                name="ПЛА",
                description="План ликвидации аварий",
                category="plan",
                builder=_opo_emergency_plan,
            ),
            PackTemplateSpec(
                code="pack_opo_training_matrix",
                name="Матрица обучения",
                description="Матрица обучения и допусков",
                category="training",
                builder=_opo_training_matrix,
            ),
        ),
        item_order=(
            "pack_opo_passport",
            "pack_opo_emergency_plan",
            "pack_opo_training_matrix",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
        },
    ),
    PackDefinition(
        code=PACK_CODE_WASTE,
        name="Отходы/экология",
        description="Минимальный пакет для обращения с отходами",
        scenario=PackScenario.WASTE,
        module=DocumentPackModule.HEALTH,
        scenario_type=DocumentPackScenario.DOCUMENT_BATCH,
        templates=(
            PackTemplateSpec(
                code="pack_waste_register",
                name="Реестр",
                description="Реестр отходов",
                category="register",
                builder=_waste_register,
            ),
            PackTemplateSpec(
                code="pack_waste_contract",
                name="Договор",
                description="Договор с подрядчиком",
                category="contract",
                builder=_waste_contract,
            ),
            PackTemplateSpec(
                code="pack_waste_briefing",
                name="Памятка",
                description="Инструктаж по обращению с отходами",
                category="instruction",
                builder=_waste_briefing,
            ),
        ),
        item_order=(
            "pack_waste_register",
            "pack_waste_contract",
            "pack_waste_briefing",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
        },
    ),
    PackDefinition(
        code=PACK_CODE_CEO_SHIELD,
        name="Щит генерального директора",
        description="Базовый пакет для распределения ответственности и контроля",
        scenario=PackScenario.CEO_SHIELD,
        module=DocumentPackModule.FIRE_SAFETY,
        scenario_type=DocumentPackScenario.DOCUMENT_BATCH,
        templates=(
            PackTemplateSpec(
                code="pack_ceo_order",
                name="Приказ",
                description="Приказ генерального директора",
                category="order",
                builder=_ceo_order,
            ),
            PackTemplateSpec(
                code="pack_ceo_delegation",
                name="Делегирование",
                description="Делегирование полномочий",
                category="delegation",
                builder=_ceo_delegation,
            ),
            PackTemplateSpec(
                code="pack_ceo_control_card",
                name="Контроль",
                description="Карта контроля директора",
                category="control",
                builder=_ceo_control_card,
            ),
        ),
        item_order=(
            "pack_ceo_order",
            "pack_ceo_delegation",
            "pack_ceo_control_card",
        ),
        metadata={
            "logo": build_inline_image_descriptor(DEFAULT_LOGO_BYTES)["data"],
            "stamp": build_inline_image_descriptor(DEFAULT_STAMP_BYTES)["data"],
        },
    ),
)

PACK_DEFINITIONS_BY_CODE: dict[str, PackDefinition] = {pack.code: pack for pack in DEFAULT_PACKS}
