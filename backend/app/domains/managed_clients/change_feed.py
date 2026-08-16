"""Лента изменений у клиента (BIZ-51 срез-1, Доп. №1 разд. 51.1).

Разд. 51 превращает разовую услугу в подписное сопровождение: аутсорсер обязан
отслеживать изменения в компании заказчика и заранее готовить документы. Сегодня
такой ленты нет вовсе — есть «Центр внимания» (BIZ-49), но он про ПРОСРОЧКИ,
то есть про состояние, а не про события; принятый сотрудник или новая площадка
в нём не появятся, пока по ним что-нибудь не просрочится.

**Первый срез фиксирует изменения и подсказывает, что делать, но НИЧЕГО не
создаёт сам.** ТЗ говорит «предложить/сделать автоматически» — начинать с
«сделать» нельзя: одна загрузка штатки на сотню человек породила бы сотни задач
и инструктажей, а разгребать их пришлось бы вручную. Сначала специалист видит
список и решает; автосоздание — отдельный шаг, когда правила обкатаны.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ClientChangeKind(str, enum.Enum):
    """Виды изменений из таблицы разд. 51.1 — закрытым списком.

    Список закрыт: на каждый вид ТЗ задаёт СВОИ последствия, и «прочее» без
    последствий превратило бы ленту в свалку заметок.
    """

    EMPLOYEE_HIRED = "employee_hired"
    EMPLOYEE_LEFT = "employee_left"
    POSITION_ADDED = "position_added"
    SITE_ADDED = "site_added"
    ORG_STRUCTURE_CHANGED = "org_structure_changed"
    ACTIVITY_CHANGED = "activity_changed"
    DEADLINE_APPROACHING = "deadline_approaching"
    REGULATION_CHANGED = "regulation_changed"


#: Человеческие названия видов: лента читается специалистом, а не машиной.
CHANGE_TITLES: dict[ClientChangeKind, str] = {
    ClientChangeKind.EMPLOYEE_HIRED: "Принят новый сотрудник",
    ClientChangeKind.EMPLOYEE_LEFT: "Уволен или переведён сотрудник",
    ClientChangeKind.POSITION_ADDED: "Новая должность или рабочее место",
    ClientChangeKind.SITE_ADDED: "Новый объект или площадка",
    ClientChangeKind.ORG_STRUCTURE_CHANGED: "Изменение оргструктуры",
    ClientChangeKind.ACTIVITY_CHANGED: "Изменение вида деятельности или оборудования",
    ClientChangeKind.DEADLINE_APPROACHING: "Наступает срок",
    ClientChangeKind.REGULATION_CHANGED: "Изменение НПА",
}

#: Что предложить по каждому виду. Тексты — прямо из таблицы разд. 51.1: это
#: обязательства, которые ТЗ перечисляет поимённо, и переписывать их «своими
#: словами» значило бы тихо изменить объём услуги.
CHANGE_SUGGESTIONS: dict[ClientChangeKind, tuple[str, ...]] = {
    ClientChangeKind.EMPLOYEE_HIRED: (
        "Вводный и первичный инструктаж",
        "Направление на медосмотр",
        "Карточка и выдача СИЗ",
        "Ознакомление с инструкциями",
    ),
    ClientChangeKind.EMPLOYEE_LEFT: (
        "Закрытие карточек",
        "Возврат СИЗ",
        "Отзыв допусков",
        "Актуализация журналов",
    ),
    ClientChangeKind.POSITION_ADDED: (
        "Пересчёт норм СИЗ",
        "Требования по обучению",
        "Оценка рисков",
        "Набор обязательных инструкций",
    ),
    ClientChangeKind.SITE_ADDED: (
        "Проверка обязательного пакета по объекту",
        "Назначение ответственных",
        "Пакет допуска",
    ),
    ClientChangeKind.ORG_STRUCTURE_CHANGED: (
        "Пересчёт назначений и ответственных",
        "Маршруты согласования",
    ),
    ClientChangeKind.ACTIVITY_CHANGED: (
        "Пересмотр рисков",
        "Обязательства по СОУТ",
        "Требования ПромБез и ОПО",
        "Пожарные требования",
    ),
    ClientChangeKind.DEADLINE_APPROACHING: (
        "Задача на продление",
        "Генерация комплекта заранее",
    ),
    ClientChangeKind.REGULATION_CHANGED: (
        "Разбор влияния: какие документы устарели",
        "Задачи на актуализацию",
    ),
}


class ChangeStatus(str, enum.Enum):
    """Что специалист сделал с изменением.

    `dismissed` существует намеренно: часть изменений не требует действий
    (перевод внутри отдела без смены рабочего места), и без «отклонить» лента
    копила бы вечные долги, а специалист перестал бы её открывать.
    """

    NEW = "new"
    HANDLED = "handled"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class ChangeSummary:
    """Сводка по ленте: сколько требует внимания."""

    total: int
    new: int

    @property
    def text(self) -> str:
        if self.total == 0:
            return "Изменений не зафиксировано"
        if self.new == 0:
            return f"Все изменения разобраны: {self.total}"
        return f"Требуют внимания: {self.new} из {self.total}"


def suggestions_for(kind: ClientChangeKind) -> list[str]:
    """Что предложить по изменению. Пустого списка не бывает.

    Каждый вид ленты обязан отвечать на вопрос «и что теперь делать»: запись без
    последствий — это заметка, а лента заводилась ради обязательств.
    """

    return list(CHANGE_SUGGESTIONS[kind])


def title_for(kind: ClientChangeKind) -> str:
    return CHANGE_TITLES[kind]
