"""Лента изменений у клиента (BIZ-51 срез-1, Доп. №1 разд. 51.1)."""

from __future__ import annotations

from app.domains.managed_clients.change_feed import (
    CHANGE_SUGGESTIONS,
    CHANGE_TITLES,
    ChangeStatus,
    ChangeSummary,
    ClientChangeKind,
    suggestions_for,
    title_for,
)


def test_виды_изменений_совпадают_с_таблицей_тз():
    """Разд. 51.1 перечисляет ровно восемь строк — ни больше, ни меньше."""

    assert len(list(ClientChangeKind)) == 8
    assert ClientChangeKind.EMPLOYEE_HIRED in ClientChangeKind
    assert ClientChangeKind.REGULATION_CHANGED in ClientChangeKind


def test_у_каждого_вида_есть_название_и_подсказки():
    # Запись без последствий — заметка, а лента заводилась ради обязательств.
    for kind in ClientChangeKind:
        assert CHANGE_TITLES[kind]
        assert CHANGE_SUGGESTIONS[kind], kind


def test_подсказки_взяты_из_тз_дословно():
    # Переписать «своими словами» значило бы тихо изменить объём услуги.
    hired = suggestions_for(ClientChangeKind.EMPLOYEE_HIRED)

    assert "Вводный и первичный инструктаж" in hired
    assert "Направление на медосмотр" in hired
    assert "Карточка и выдача СИЗ" in hired
    assert "Ознакомление с инструкциями" in hired


def test_увольнение_предлагает_закрытие_а_не_оформление():
    left = suggestions_for(ClientChangeKind.EMPLOYEE_LEFT)

    assert "Возврат СИЗ" in left
    assert "Отзыв допусков" in left
    assert "Направление на медосмотр" not in left


def test_подсказки_нельзя_испортить_снаружи():
    # Список отдаётся наружу в ответе API; общий кортеж защищает от того, что
    # вызывающий его «поправит» и испортит подсказки всем остальным.
    first = suggestions_for(ClientChangeKind.SITE_ADDED)
    first.append("выдуманное")

    assert "выдуманное" not in suggestions_for(ClientChangeKind.SITE_ADDED)


def test_название_вида_человеческое():
    assert title_for(ClientChangeKind.SITE_ADDED) == "Новый объект или площадка"


def test_статусы_включают_отклонение():
    # Без «отклонить» лента копила бы вечные долги: часть изменений действий не
    # требует, и специалист перестал бы её открывать.
    assert ChangeStatus.DISMISSED in ChangeStatus


def test_сводка_различает_пусто_и_всё_разобрано():
    # «Пусто» и «всё разобрано» — разные ответы, и различать их по длине списка
    # человек не обязан.
    assert ChangeSummary(total=0, new=0).text == "Изменений не зафиксировано"
    assert ChangeSummary(total=5, new=0).text == "Все изменения разобраны: 5"


def test_сводка_называет_сколько_требует_внимания():
    assert ChangeSummary(total=5, new=2).text == "Требуют внимания: 2 из 5"
