"""Связь «работник ↔ пользователь» — одна формула на продукт (BIZ-54-57 срез-119).

ЗАЧЕМ. Прямой ссылки между ``Person`` и ``User`` в моделях нет: их сопоставляют
по почте без учёта регистра. Пока копий было две (карточка сотрудника и Центр
внимания), правило уже переехало в ``services/person_link`` — а срез-118 завёл
третью, в движке правил, и она сразу отличалась мелочью (проверкой пустой
почты). Цена расхождения тут не косметическая: в одну сторону покажем чужую
учётную запись, в другую — отправим человеку чужое уведомление.

ЧТО ПРОВЕРЯЕТСЯ: сравнение почт ``Person`` и ``User`` написано ровно в одном
файле; обе стороны связи ходят в одну сторону арендатора.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.services.person_link import resolve_person_id, resolve_user, resolve_user_id

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Единственное место, где формула НАПИСАНА; остальные обязаны её импортировать.
FORMULA_HOME = "services/person_link.py"

#: Сравнение почты пользователя с почтой работника (в любую сторону).
_MATCH = re.compile(
    r"func\.lower\((User|Person)\.email\)\s*==\s*"
    r"(str\()?(person|user)[\w.]*\.?email|"
    r"func\.lower\((User|Person)\.email\)\s*==\s*\w*person\w*"
)


def test_сторож_сопоставление_почт_пишется_один_раз() -> None:
    """Своя копия сопоставления разойдётся с остальными на первой правке."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        if _MATCH.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        "связь «работник ↔ пользователь» написана заново — возьмите "
        f"resolve_user / resolve_person_id из {FORMULA_HOME}: {offenders}"
    )


def test_обе_стороны_связи_на_месте() -> None:
    """Направления два, и оба обязаны жить здесь, иначе вернутся копии."""

    assert callable(resolve_person_id)
    assert callable(resolve_user)
    assert callable(resolve_user_id)


@pytest.mark.asyncio
async def test_пустая_почта_не_ищется(sessionmaker) -> None:
    """Работник без почты — законный исход, а не повод достать первого попавшегося."""

    async with sessionmaker() as session:
        assert await resolve_user(session, "t1", None) is None
        assert await resolve_user_id(session, "t1", "") is None
        assert await resolve_person_id(session, "t1", None) is None
