"""Библиотека предустановленных правил по дисциплинам (BIZ-54-57 срез-4).

Доп. №1 разд. 57.3: «Библиотека предустановленных правил по каждой дисциплине
(поставляется как starter-pack) — это и есть зашитая экспертиза, заменяющая
ручной анализ специалиста». Приёмка §58.3 требует того же отдельной строкой.

**Что нашла сверка.** Движок правил в продукте есть и работает: событие →
условия → действия (задача / уведомление / вебхук). А предустановленных правил
не было НИ ОДНОГО. Два правила существовали только у демонстрационного
арендатора, заведённые прямо в коде демо-посева: настоящий новый клиент получал
пустой движок и должен был придумывать экспертизу сам. «Конструктор есть» и
«экспертиза поставляется» — разные утверждения.

## Правило пишется только на СУЩЕСТВУЮЩЕЕ событие

Правило живёт от события. Поэтому дисциплина получает правила ровно тогда,
когда в продукте есть событие, из которого она следует **однозначно**:

* медосмотры, СИЗ, обучение — свои события есть давно;
* пожарная и промышленная безопасность — получили своё первое событие в этом
  срезе (``WorkPermitIssued``): вид работ у наряда-допуска закрытый, и у двух
  видов дисциплина следует из закона (огневые → ПБ по Правилам противопожарного
  режима, газоопасные → ПромБез по ФНП Ростехнадзора);
* экология, ГО-ЧС и БДД событий не имели вовсе — до среза-62 правил для них
  здесь НЕ было, с названной причиной. Срез-62 дал им событие, общее для
  всех сроков дисциплин: ``DisciplineDeadlineOverdue`` — просрочка строки
  ОБЩЕГО календаря (разрешение и замер ПЭК, ЭПБ устройства, учение ГО,
  документ ТС, водительское удостоверение). Дисциплина и источник в нём —
  закрытые словари, поэтому условие точное; правила ниже висят на нём.

**Почему не «хоть какое-нибудь правило».** Единственное, за что можно было бы
зацепиться у экологии или ПБ до среза-62, — свободный текст (название
проверки, надзорный орган). Правило на свободный текст срабатывает у того,
кто написал «МЧС», и молчит у того, кто написал «Госпожнадзор». Это угадайка,
проданная под видом экспертизы: специалист будет уверен, что система его
страхует, а она не страхует. Пустая клетка с причиной честнее — и она стояла
пустой, пока не появилось событие, на которое можно подписаться точно.

Правила чистые: здесь только данные и разметка, без базы и без сессий.
Валидность каждого правила для самого движка (событие существует, условия и
действия проходят разбор, поля условий есть в payload события) стережёт
``tests/test_rules_library.py`` — библиотека, которую движок не примет, не
сработает никогда и была бы худшим видом «поставленной экспертизы».
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from app.core.disciplines import DISCIPLINE_TITLES, Discipline

__all__ = [
    "DISCIPLINES_WITHOUT_RULES",
    "LIBRARY_RULES",
    "LibraryRule",
    "coverage",
    "rules_for",
]


@dataclass(frozen=True)
class LibraryRule:
    """Одно правило библиотеки — ровно то, что примет движок, плюс дисциплина."""

    discipline: Discipline
    name: str
    description: str
    event_type: str
    conditions: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    priority: int = 100


LIBRARY_RULES: tuple[LibraryRule, ...] = (
    # ── Медосмотры ──────────────────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.MEDICAL,
        name="Медосмотр: заключение «не годен» — отстранить",
        description=(
            "Заключение «не годен» обязывает не допускать работника к работе. "
            "Правило ставит задачу оформить отстранение и предупреждает "
            "специалиста по охране труда и кадры."
        ),
        event_type="MedicalExamRecorded",
        conditions={
            "match": "all",
            "conditions": [{"field": "fitness", "op": "eq", "value": "unfit"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "Оформить отстранение по медосмотру (заключение: {fitness})",
                "priority": "critical",
                "due_in_days": 1,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Медосмотр: «не годен»",
                "body_template": "По медосмотру {exam_id} вынесено «не годен» — работник не допускается к работе.",
                "recipient_mode": "role",
                "roles": ["ot_specialist", "hr"],
                "priority": "critical",
            },
        ],
        priority=10,
    ),
    LibraryRule(
        discipline=Discipline.MEDICAL,
        name="Медосмотр: «годен с ограничениями» — сверить условия труда",
        description=(
            "Ограничения в заключении имеют смысл, только если их сверили с "
            "фактическими условиями труда и при необходимости перевели работника."
        ),
        event_type="MedicalExamRecorded",
        conditions={
            "match": "all",
            "conditions": [{"field": "fitness", "op": "eq", "value": "fit_with_restrictions"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "Сверить условия труда с ограничениями медосмотра",
                "priority": "high",
                "due_in_days": 3,
                "assignee_mode": "none",
            }
        ],
        priority=20,
    ),
    # ── СИЗ ─────────────────────────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.PPE,
        name="СИЗ: срок носки истекает — выдать замену",
        description=(
            "Истекающий срок носки — это будущий разрыв с нормой. Задача "
            "ставится заранее, чтобы замена нашлась до того, как СИЗ станет "
            "просроченным."
        ),
        event_type="PPEReplacementDue",
        conditions={},
        actions=[
            {
                "type": "create_task",
                "title_template": "Выдать замену СИЗ: {item_name}",
                "priority": "high",
                "due_in_days": 7,
                "assignee_mode": "none",
            }
        ],
        priority=30,
    ),
    # ── Обучение ────────────────────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.TRAINING,
        name="Обучение: проверка знаний пройдена — оформить протокол",
        description=(
            "Пройденная проверка знаний без протокола и удостоверения "
            "юридически не существует: инспектор смотрит документы, а не запись "
            "в системе."
        ),
        event_type="TrainingCompleted",
        conditions={},
        actions=[
            {
                "type": "create_task",
                "title_template": "Оформить протокол и удостоверение по обучению",
                "priority": "medium",
                "due_in_days": 5,
                "assignee_mode": "none",
            }
        ],
        priority=40,
    ),
    LibraryRule(
        discipline=Discipline.TRAINING,
        name="Обучение: истёк срок удостоверения — направить на переобучение",
        description=(
            "Работника, не прошедшего в установленном порядке обучение и проверку "
            "знаний по охране труда, работодатель обязан отстранить от работы "
            "(ТК РФ ст. 76, Порядок обучения — ПП РФ № 2464). Срок истекает у "
            "конкретного удостоверения конкретного человека (срез-75); правило "
            "ставит задачу направить на переобучение и предупреждает специалиста "
            "по ОТ и кадры. Задача на три дня: переобучение надо организовать, "
            "а не просто отметить."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "training_certificate"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: срок истёк — направить на переобучение",
                "priority": "high",
                "due_in_days": 3,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Истёк срок удостоверения по обучению",
                "body_template": "{title} — срок истёк, просрочка {days_overdue} дн.; до переобучения к работам по нему не допускать.",
                "recipient_mode": "role",
                "roles": ["ot_specialist", "hr"],
                "priority": "high",
            },
        ],
        priority=20,
    ),
    LibraryRule(
        discipline=Discipline.TRAINING,
        name="Обучение: срок назначения истёк — обеспечить прохождение",
        description=(
            "Назначенное обучение работник обязан пройти в установленный срок; "
            "работодатель обязан обеспечить обучение и не допускать к работе не "
            "прошедших его (ТК РФ ст. 214, 76; ПП РФ № 2464). Срок назначения "
            "истекает у конкретного человека (срез-77); правило ставит задачу "
            "обеспечить прохождение — назначить дату, напомнить, при нужде "
            "отстранить — и предупреждает специалиста по ОТ и кадры. Задача на "
            "три дня: сдать обучение за день нельзя, но и тянуть месяц — тоже."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "training_enrollment"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: срок истёк — обеспечить прохождение обучения",
                "priority": "high",
                "due_in_days": 3,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Истёк срок назначенного обучения",
                "body_template": "{title} — срок истёк, просрочка {days_overdue} дн.; назначить дату и напомнить работнику.",
                "recipient_mode": "role",
                "roles": ["ot_specialist", "hr"],
                "priority": "high",
            },
        ],
        priority=20,
    ),
    # ── Пожарная безопасность ───────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.FIRE_SAFETY,
        name="ПБ: выдан наряд на огневые работы — проверить пожарные меры",
        description=(
            "Огневые работы ведутся по наряду-допуску согласно Правилам "
            "противопожарного режима: до начала нужны средства пожаротушения на "
            "месте, очищенная зона и назначенный наблюдающий."
        ),
        event_type="WorkPermitIssued",
        conditions={
            "match": "all",
            "conditions": [{"field": "work_type", "op": "eq", "value": "hot_work"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "Огневые работы {number}: проверить средства пожаротушения и наблюдающего",
                "priority": "critical",
                "due_in_days": 0,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Огневые работы начаты",
                "body_template": "Выдан наряд-допуск на огневые работы в зоне: {zone_text}.",
                "recipient_mode": "role",
                "roles": ["pb_engineer"],
                "priority": "high",
            },
        ],
        priority=15,
    ),
    # ── Промышленная безопасность ───────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.INDUSTRIAL_SAFETY,
        name="ПромБез: выдан наряд на газоопасные работы — проверить газовую среду",
        description=(
            "Газоопасные работы ведутся по ФНП Ростехнадзора: до начала нужен "
            "анализ воздушной среды, средства защиты органов дыхания и "
            "оформленные меры безопасности."
        ),
        event_type="WorkPermitIssued",
        conditions={
            "match": "all",
            "conditions": [{"field": "work_type", "op": "eq", "value": "gas_hazardous"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "Газоопасные работы {number}: анализ воздушной среды и СИЗОД",
                "priority": "critical",
                "due_in_days": 0,
                "assignee_mode": "none",
            }
        ],
        priority=15,
    ),
    LibraryRule(
        discipline=Discipline.INDUSTRIAL_SAFETY,
        name="ПромБез: истёк срок ЭПБ — не эксплуатировать устройство до заключения",
        description=(
            "Техническое устройство на ОПО без действующего заключения экспертизы "
            "промышленной безопасности эксплуатировать нельзя (116-ФЗ, ст. 7 и 13). "
            "Правило ставит задачу вывести устройство из работы и заказать ЭПБ."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "industrial_safety_epb"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: остановить до нового заключения ЭПБ",
                "priority": "critical",
                "due_in_days": 0,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "ЭПБ просрочена",
                "body_template": "{title} — срок заключения истёк, просрочка {days_overdue} дн.",
                "recipient_mode": "role",
                "roles": ["pb_engineer"],
                "priority": "critical",
            },
        ],
        priority=15,
    ),
    # ── Экология ────────────────────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.ECOLOGY,
        name="Экология: истёк срок разрешения — переоформить",
        description=(
            "Выброс или сброс без действующего разрешения — нарушение (КоАП РФ "
            "ст. 8.21 и 8.14) с приостановкой деятельности в риске. Разрешение "
            "переоформляют месяцами, поэтому задача ставится сразу и срочно."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "ecology_permit"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: срок истёк — переоформить разрешение",
                "priority": "critical",
                "due_in_days": 1,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Разрешение истекло",
                "body_template": "{title} — срок истёк, просрочка {days_overdue} дн.",
                "recipient_mode": "role",
                "roles": ["ecologist"],
                "priority": "critical",
            },
        ],
        priority=15,
    ),
    LibraryRule(
        discipline=Discipline.ECOLOGY,
        name="Экология: пропущен плановый замер ПЭК — провести",
        description=(
            "Пропущенный замер по плану-графику ПЭК — дыра в отчётности, которую "
            "инспектор увидит по датам. Задача — провести замер и внести результат."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "ecology_measurement"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: плановая дата прошла — провести замер",
                "priority": "high",
                "due_in_days": 3,
                "assignee_mode": "none",
            }
        ],
        priority=30,
    ),
    LibraryRule(
        discipline=Discipline.ECOLOGY,
        name="Экология: пропущен срок отчётности или платежа — сдать и уплатить",
        description=(
            "Несданная 2-ТП или декларация о плате — штраф (КоАП РФ ст. 8.5), "
            "неуплаченная плата за НВОС — штраф и пени (ст. 8.41). Срок вносит "
            "эколог; событие приходит только по несданному — исполненный срок "
            "календарь не отдаёт. Задача ставится на завтра: каждый день "
            "просрочки дорожает."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "ecology_report"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: срок прошёл — сдать и отметить исполнение",
                "priority": "high",
                "due_in_days": 1,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Пропущен срок отчётности",
                "body_template": "{title} — срок прошёл, просрочка {days_overdue} дн.",
                "recipient_mode": "role",
                "roles": ["ecologist"],
                "priority": "high",
            },
        ],
        priority=20,
    ),
    # ── ГО и ЧС ─────────────────────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.CIVIL_DEFENSE,
        name="ГО и ЧС: учение не проведено в срок — назначить новую дату",
        description=(
            "Учение или тренировка из плана-графика не проведены к плановой дате. "
            "Без протокола учение не состоялось: задача — провести и оформить "
            "либо перенести с внесением новой даты в план."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "civil_defense_drill"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: плановая дата прошла — провести или перенести",
                "priority": "high",
                "due_in_days": 3,
                "assignee_mode": "none",
            }
        ],
        priority=30,
    ),
    # ── БДД ─────────────────────────────────────────────────────────────────
    LibraryRule(
        discipline=Discipline.ROAD_SAFETY,
        name="БДД: истёк срок водительского удостоверения — отстранить от рейсов",
        description=(
            "Водитель с истёкшим удостоверением к управлению не допускается "
            "(ПДД п. 2.1.1, КоАП РФ ст. 12.7). Правило ставит задачу отстранить "
            "от рейсов до замены удостоверения и предупреждает кадры."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "road_safety_driver"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: срок истёк — отстранить от рейсов",
                "priority": "critical",
                "due_in_days": 0,
                "assignee_mode": "none",
            },
            {
                "type": "notify",
                "title_template": "Удостоверение водителя истекло",
                "body_template": "{title} — срок истёк, просрочка {days_overdue} дн.; к рейсам не допускать.",
                "recipient_mode": "role",
                "roles": ["ot_specialist", "hr"],
                "priority": "critical",
            },
        ],
        priority=10,
    ),
    LibraryRule(
        discipline=Discipline.ROAD_SAFETY,
        name="БДД: просрочен документ ТС — снять с линии до переоформления",
        description=(
            "Без действующего техосмотра, ОСАГО, лицензии на перевозки или "
            "поверки тахографа выпускать машину на линию нельзя (КоАП РФ "
            "ст. 12.1, 12.37, 11.23). Задача — снять ТС с линии и переоформить."
        ),
        event_type="DisciplineDeadlineOverdue",
        conditions={
            "match": "all",
            "conditions": [{"field": "source_type", "op": "eq", "value": "road_safety_vehicle"}],
        },
        actions=[
            {
                "type": "create_task",
                "title_template": "{title}: срок истёк — снять с линии и переоформить",
                "priority": "critical",
                "due_in_days": 0,
                "assignee_mode": "none",
            }
        ],
        priority=15,
    ),
)


#: Дисциплины, для которых правил НЕТ, и почему. Пустая клетка с причиной
#: честнее выдуманного правила: молчание однажды прочитают как «забыли».
#:
#: СВЕРКА 2026-09-05 (срез-62): словарь ПУСТ. Экология, ГО и ЧС и БДД три
#: сверки подряд стояли здесь с причиной «контур не испускает событий» —
#: причина была правдивой, но приёмка §58.3 требует правил для КАЖДОЙ
#: дисциплины. Срез-62 дал сквозное событие ``DisciplineDeadlineOverdue``
#: (просрочка строки общего календаря), и клетки заполнены. Словарь оставлен
#: с сторожами: если дисциплина когда-нибудь снова останется без правил,
#: причина обязана быть здесь и обязана говорить о СОБЫТИЯХ.
DISCIPLINES_WITHOUT_RULES: dict[Discipline, str] = {}


def rules_for(discipline: Discipline) -> tuple[LibraryRule, ...]:
    """Правила библиотеки по одной дисциплине (в объявленном порядке)."""

    return tuple(rule for rule in LIBRARY_RULES if rule.discipline is discipline)


def coverage(*, alive: Collection[str] = (), deleted: Collection[str] = ()) -> list[dict[str, Any]]:
    """Покрытие по ВСЕМ дисциплинам ТЗ: сколько правил или почему их нет.

    Порядок — как в словаре дисциплин: список читают регулярно, и скачущие
    строки мешают сравнивать.

    ``alive`` / ``deleted`` — имена правил библиотеки, которые у арендатора
    живут / удалены специалистом (срез-66). По ним строка называет ИМЕНА:
    ``missing`` — ни разу не выданные, ``removed`` — убранные самим
    специалистом. Число «выдано 10 из 12» без имён заставляло гадать, каких
    двух не хватает и вернёт ли их кнопка.
    """

    alive_names = set(alive)
    deleted_names = set(deleted)
    rows: list[dict[str, Any]] = []
    for discipline in Discipline:
        rules = rules_for(discipline)
        rows.append(
            {
                "discipline": discipline.value,
                "title": DISCIPLINE_TITLES[discipline],
                "rules": len(rules),
                "reason": "" if rules else DISCIPLINES_WITHOUT_RULES.get(discipline, ""),
                "missing": [
                    rule.name
                    for rule in rules
                    if rule.name not in alive_names and rule.name not in deleted_names
                ],
                "removed": [rule.name for rule in rules if rule.name in deleted_names],
            }
        )
    return rows
