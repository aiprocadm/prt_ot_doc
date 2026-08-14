"""Правила принятия юридических текстов (BIZ-52 срез-11, Доп. №1 разд. 52.2)."""

from __future__ import annotations

from app.domains.reseller.legal_acceptance import (
    AcceptanceState,
    document_fingerprint,
    pending_kinds,
)


def _state(current: int | None, accepted: int | None, kind: str = "offer") -> AcceptanceState:
    return AcceptanceState(kind=kind, current_version=current, accepted_version=accepted)


def test_принята_действующая_редакция():
    assert _state(3, 3).accepted is True


def test_принята_прежняя_редакция_значит_не_принято():
    # Условия изменились; согласие с прежними на новые не переносится, иначе
    # публикация новой оферты молча считалась бы принятой всеми.
    state = _state(4, 3)

    assert state.accepted is False
    assert state.outdated is True


def test_не_принимал_вовсе_это_не_устаревание():
    # Разные сообщения человеку: «примите оферту» и «условия изменились».
    state = _state(2, None)

    assert state.accepted is False
    assert state.outdated is False


def test_текста_нет_принимать_нечего():
    state = _state(None, None)

    assert state.exists is False
    assert state.accepted is False
    assert state.outdated is False


def test_текста_нет_а_принятие_есть_не_требует_подписи():
    # Партнёр может снять текст; висящее требование подписи под несуществующим
    # документом заперло бы человека в баннере навсегда.
    assert _state(None, 2).accepted is False
    assert pending_kinds([_state(None, 2)]) == []


def test_список_к_подписи_сохраняет_порядок():
    states = [
        _state(1, 1, kind="offer"),
        _state(2, None, kind="privacy"),
        _state(3, 2, kind="consent"),
    ]

    assert pending_kinds(states) == ["privacy", "consent"]


def test_отпечаток_различает_тексты():
    assert document_fingerprint("Оферта") != document_fingerprint("Оферта.")


def test_отпечаток_одинакового_текста_совпадает():
    assert document_fingerprint("Условия") == document_fingerprint("Условия")


def test_отпечаток_считается_от_кириллицы_без_поломки():
    # Текст оферты русский; кодировка по умолчанию должна быть явной, иначе
    # отпечаток зависел бы от настроек машины.
    value = document_fingerprint("Публичная оферта «Партнёр»")

    assert len(value) == 64
    assert value.isascii()
