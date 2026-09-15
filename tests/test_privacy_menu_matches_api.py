"""Сторож: пункт меню ПДн не шире, чем ручки ПДн (срез-208).

ЗАЧЕМ ИМЕННО ЭТОТ СТОРОЖ. У платформы есть открытый дефект, записанный в
``docs/audit/ACCESS_MENU_VS_API.md``: **51 пункт меню виден роли, которой ручка
откажет.** Человек видит раздел, заходит и получает отказ — и решает, что
сломана платформа.

Заводя первую витрину контура ПДн, легко повторить ровно это: роль
``ot_pb_head`` получает права СКОПОМ (``ALL_PERMISSIONS`` минус одно), а ручки
ПДн открыты только ``admin``/``owner``/``hr``. Без явного исключения пункт меню
появился бы у роли, которой ручка отвечает 403.

ЧЕМ ЭТОТ СТОРОЖ НЕ ЯВЛЯЕТСЯ. Он читает ТЕКСТ файла прав витрины — это разбор по
исходнику, и он не поймает выдачу права через переменную или вычисление. Граница
названа честно; сторож ловит ту форму записи, которой в этом файле пользуются
все, и не даёт разойтись двум спискам ролей.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_privacy_menu_matches_api.py -v``.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.privacy.api import _PDN_ROLES

REPO_ROOT = Path(__file__).resolve().parents[1]
PERMISSIONS_TS = REPO_ROOT / "frontend" / "src" / "permissions" / "permissions.ts"

#: Роли, которым право выдаётся СКОПОМ (весь каталог). Их разбор по списку не
#: увидит — они перечислены здесь и проверяются отдельно.
_BULK_ROLES = ("owner", "admin", "ot_pb_head")


def _source() -> str:
    return PERMISSIONS_TS.read_text(encoding="utf-8")


def _roles_with_explicit_grant(permission_key: str) -> set[str]:
    """Роли, у которых право перечислено СПИСКОМ.

    Разбор ПОСТРОЧНЫЙ, а не регулярным выражением: первая версия сторожа была
    на регулярке с «.*?» через строки, и она склеивала однострочный блок
    (``student: [A, B],``) со следующими — приписывая право роли, у которой его
    нет. Поймала это проверка ``test_разбор_видит_выдачу_права``: сторож по
    тексту молчит и когда всё хорошо, и когда сломан он сам.
    """

    roles: set[str] = set()
    current: str | None = None
    needle = f"PERMISSIONS.{permission_key}"
    for line in _source().splitlines():
        start = re.match(r"^  ([a-z_]+): \[", line)
        if start:
            current = start.group(1)
            # Однострочный блок закрывается здесь же.
            if "]" in line:
                if needle in line:
                    roles.add(current)
                current = None
                continue
        if current is None:
            continue
        if needle in line:
            roles.add(current)
        if line.startswith("  ],"):
            current = None
    return roles


def test_право_пдн_объявлено() -> None:
    assert "PRIVACY_VIEW:" in _source(), "право витрины ПДн не заведено"


def test_меню_пдн_не_шире_ручек() -> None:
    """ГЛАВНАЯ ПРОВЕРКА СРЕЗА.

    Круг ролей витрины обязан совпасть с кругом ролей ручек. Шире — человек
    увидит раздел и получит отказ; уже — обязанность по 152-ФЗ окажется
    недоступна тому, кто её исполняет.
    """

    explicit = _roles_with_explicit_grant("PRIVACY_VIEW")
    # owner и admin получают весь каталог — они в круге ручек, и это верно.
    granted = explicit | {"owner", "admin"}

    assert granted == set(_PDN_ROLES), (
        "круг ролей витрины ПДн разошёлся с ручками:\n"
        f"  витрина: {sorted(granted)}\n"
        f"  ручки:   {sorted(_PDN_ROLES)}\n"
        "Это ровно тот дефект, что описан в docs/audit/ACCESS_MENU_VS_API.md."
    )


def test_роль_получающая_права_скопом_исключена_явно() -> None:
    """``ot_pb_head`` берёт весь каталог минус исключения. Право ПДн обязано
    быть среди исключений — иначе пункт меню появится у роли, которой ручка
    ответит 403, и никакой список это не покажет."""

    text = _source()
    block = re.search(r"ot_pb_head: ALL_PERMISSIONS\.filter\((.*?)\),\n", text, re.S)

    assert block is not None, "блок ot_pb_head изменился — сторож надо обновить"
    assert "PERMISSIONS.PRIVACY_VIEW" in block.group(1), (
        "роль ot_pb_head получает право ПДн скопом, а ручки её не пускают"
    )


def test_разбор_видит_выдачу_права() -> None:
    """Доказано поломкой: без этой проверки предыдущие зелены всегда.

    Разбор по тексту — самый лживый вид сторожа: он молчит и когда всё хорошо,
    и когда сам сломан.
    """

    roles = _roles_with_explicit_grant("PRIVACY_VIEW")

    assert "hr" in roles, "разбор не увидел выдачу права роли hr"
    assert "student" not in roles, "разбор приписал право роли, у которой его нет"
