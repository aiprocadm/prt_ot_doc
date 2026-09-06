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
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, Select, and_, not_, select

from app.models.master_data import EmploymentStatus, Person

__all__ = ["employed_person_where", "not_employed_person_ids"]


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
