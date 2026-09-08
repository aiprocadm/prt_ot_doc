"""«Уволенный не в счёт» — одно правило на всех, кто считает людей (BIZ-54-57 срез-89).

Карточка сотрудника у уволенного светофор не считает вовсе
(``employee_card.TERMINATED_REASON``): обязательств нет. Тот же смысл обязаны
нести все поимённые счётчики — площадка 360°, светофор клиента, сводка ПБ,
сигналы портфеля: истёкший медосмотр уволенного — не разрыв с эталоном, а
история. До среза-89 условие «не удалён и не уволен» писали пять мест, а
сигналы медосмотров, СИЗ, обучения и контактов в сводке внимания по портфелю
(разд. 49.2) уволенных считали — портфель горел там, где светофор того же
клиента был чист. Теперь условия живут здесь и подставляются в любой запрос,
как у обучения (срез-77) и удостоверений (срез-88).

**Где карточки может не быть (срез-93).** Общий календарь арендатора
(``services/calendar_aggregator``) и Центр внимания на нём читают записи по
людям без join'а с ``Person`` — запись с «висячим» ``person_id`` в них видна,
и так задумано. Для таких мест то же правило дано «от обратного»:
``not_employed_person_ids`` — подзапрос людей, которых считать не надо
(удалённых и уволенных); он строится из ``employed_person_where``, а не
пишется заново, так что формула остаётся одна.

**Одно условие на запись (срез-95).** Подставлять подзапрос в каждый запрос
руками — снова пять копий, только другой формы: где-то забудут, что
``person_id`` бывает пустым (удостоверение по группе, инструктаж без
человека), и запись без человека пропадёт. Поэтому условие для записи по
человеку собирает ``employed_record_where(Model, tenant_id)``: оно само
смотрит, обязателен ли ``person_id`` у таблицы, и оставляет записи без
человека видимыми. Сторож ``tests/test_employed_person_formula.py`` не даёт
писать ``not_in(not_employed_person_ids(...))`` вне этого модуля.

**Проекции (срез-97).** Read model по человеку (``PersonComplianceReadModel``)
пересобирается, а не читается с фильтром: строка уволенного или удалённого
после пересборки должна исчезнуть, иначе сумма по проекции считает её вечно.
Условие «запись по тому, кого не в счёт» для такой чистки —
``not_employed_record_where(Model, tenant_id)``: та же формула, только
от обратного, и тоже только отсюда.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Select, and_, not_, or_, select

from app.models.master_data import EmploymentStatus, Person

__all__ = [
    "employed_person_where",
    "is_employed",
    "employed_record_where",
    "not_employed_person_ids",
    "not_employed_record_where",
]


def is_employed(person: Any) -> bool:
    """То же правило для УЖЕ ЗАГРУЖЕННОЙ записи (срез-121).

    ``employed_person_where`` собирает условия для запроса; когда человек уже
    в руках, писать сравнение заново — снова заводить копию формулы. Разница
    важна: «числится» — это всё, кроме увольнения, а не только «активен».
    """

    return (
        getattr(person, "deleted_at", None) is None
        and getattr(person, "employment_status", None) != EmploymentStatus.TERMINATED
    )


def employed_person_where() -> tuple[ColumnElement[bool], ...]:
    """Условия «работающий сотрудник»: не удалён и не уволен."""

    return (
        Person.deleted_at.is_(None),
        Person.employment_status != EmploymentStatus.TERMINATED,
    )


def not_employed_person_ids(tenant_id: str) -> Select[tuple[str]]:
    """Подзапрос: люди арендатора, которых «не в счёт» — удалённые или уволенные.

    Для запросов без join'а с ``Person`` (общий календарь, срез-93):
    ``Model.person_id.not_in(not_employed_person_ids(tenant_id))``. Отрицание
    берётся от ``employed_person_where`` — своя копия условия разошлась бы с
    остальными на первой правке словаря статусов.
    """

    return select(Person.id).where(
        Person.tenant_id == tenant_id, not_(and_(*employed_person_where()))
    )


def employed_record_where(model: type[Any], tenant_id: str) -> ColumnElement[bool]:
    """Условие «запись по работающему человеку» для таблицы с ``person_id``.

    Для запросов без join'а с ``Person`` (общий календарь, блокеры готовности,
    Командный центр, сводка БДД): человек записи не удалён и не уволен, а
    «висячий» ``person_id`` (карточки уже нет) по-прежнему виден — так было и
    до правила. Если ``person_id`` у таблицы необязателен, запись без человека
    остаётся в счёте: у неё нет того, кого можно было бы уволить.
    """

    column = model.person_id
    clause = column.not_in(not_employed_person_ids(tenant_id))
    if model.__table__.c.person_id.nullable:
        clause = or_(column.is_(None), clause)
    return clause


def not_employed_record_where(model: type[Any], tenant_id: str) -> ColumnElement[bool]:
    """Условие «запись по человеку, которого не в счёт» — для чистки проекций.

    Обратное к ``employed_record_where``: строки read model по удалённым и
    уволенным, которые пересборка должна убрать (срез-97). Запись без
    человека сюда не попадает никогда: увольнять там некого.
    """

    return model.person_id.in_(not_employed_person_ids(tenant_id))
