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
* экология, ГО-ЧС и БДД событий не имеют вовсе — и правил для них здесь НЕТ, с
  названной причиной.

**Почему не «хоть какое-нибудь правило».** Единственное, за что можно было бы
зацепиться у экологии или ПБ, — свободный текст (название проверки, надзорный
орган). Правило на свободный текст срабатывает у того, кто написал «МЧС», и
молчит у того, кто написал «Госпожнадзор». Это угадайка, проданная под видом
экспертизы: специалист будет уверен, что система его страхует, а она не
страхует. Пустая клетка с причиной честнее.

Правила чистые: здесь только данные и разметка, без базы и без сессий.
Валидность каждого правила для самого движка (событие существует, условия и
действия проходят разбор, поля условий есть в payload события) стережёт
``tests/test_rules_library.py`` — библиотека, которую движок не примет, не
сработает никогда и была бы худшим видом «поставленной экспертизы».
"""

from __future__ import annotations

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
            "conditions": [
                {"field": "fitness", "op": "eq", "value": "fit_with_restrictions"}
            ],
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
            "conditions": [
                {"field": "work_type", "op": "eq", "value": "gas_hazardous"}
            ],
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
)


#: Дисциплины, для которых правил НЕТ, и почему. Пустая клетка с причиной
#: честнее выдуманного правила: молчание однажды прочитают как «забыли».
DISCIPLINES_WITHOUT_RULES: dict[Discipline, str] = {
    Discipline.ECOLOGY: (
        "в системе нет ни одного события экологии: объектов НВОС, отходов и "
        "отчётности по ПЭК в продукте пока нет, а правило на свободный текст "
        "названия проверки было бы угадайкой, а не экспертизой"
    ),
    Discipline.CIVIL_DEFENSE: (
        "в системе нет ни одного события ГО и ЧС: ни формирований, ни учений, "
        "ни планов — вешать правило не на что"
    ),
    Discipline.ROAD_SAFETY: (
        "в системе нет ни одного события БДД: ни транспортных средств, ни "
        "предрейсовых осмотров, ни путевых листов"
    ),
}


def rules_for(discipline: Discipline) -> tuple[LibraryRule, ...]:
    """Правила библиотеки по одной дисциплине (в объявленном порядке)."""

    return tuple(rule for rule in LIBRARY_RULES if rule.discipline is discipline)


def coverage() -> list[dict[str, Any]]:
    """Покрытие по ВСЕМ дисциплинам ТЗ: сколько правил или почему их нет.

    Порядок — как в словаре дисциплин: список читают регулярно, и скачущие
    строки мешают сравнивать.
    """

    rows: list[dict[str, Any]] = []
    for discipline in Discipline:
        rules = rules_for(discipline)
        rows.append(
            {
                "discipline": discipline.value,
                "title": DISCIPLINE_TITLES[discipline],
                "rules": len(rules),
                "reason": "" if rules else DISCIPLINES_WITHOUT_RULES.get(discipline, ""),
            }
        )
    return rows
