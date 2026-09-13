"""Сторож: карточка сотрудника знает все статусы выдачи СИЗ (срез-160).

ЗАЧЕМ. В карточке сотрудника список выданных СИЗ показывает статус по
словарю подписей. Словарь знал три значения из пяти: «Списано»
(``written_off``) и «Заменено» (``replaced``) в нём не было, а подстановка
при промахе отдаёт сам код — человек видел в таблице `written_off`
латиницей. Оба статуса живые: списание идёт ручкой снятия СИЗ, замена
появляется при истечении срока носки.

Тот же класс, что сторожа словарей происшествий и проверок (срез-150),
ролей получателей (срез-148) и подписей событий конструктора правил
(срез-159): список ведётся руками, сверять его нечем.

КАК ПРОВЕРЯЕТСЯ. Словарь читается из исходника карточки, состав сверяется с
перечислением сервера в обе стороны. Подпись обязана отличаться от кода и
быть по-русски — иначе «подпись есть» превращается в отписку.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.ppe import PPEIssueStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE_CARD = REPO_ROOT / "frontend" / "src" / "pages" / "employees" / "EmployeeCardPage.tsx"


def _labels() -> dict[str, str]:
    text = EMPLOYEE_CARD.read_text(encoding="utf-8")
    marker = "const PPE_ISSUE_STATUS_LABELS"
    assert marker in text, "словарь статусов выдачи СИЗ переехал из карточки сотрудника"
    block = text.split(marker, 1)[1].split("};", 1)[0]
    return dict(re.findall(r'^\s*"?([a-z_]+)"?:\s*"([^"]+)"', block, re.M))


def test_словарь_читается() -> None:
    labels = _labels()
    assert labels.get("issued") == "Выдано", f"чтение словаря сломалось: {labels}"


def test_карточка_знает_все_статусы_выдачи_сиз() -> None:
    labels = _labels()
    server = {status.value for status in PPEIssueStatus}

    missing = sorted(server - set(labels))
    assert not missing, "карточка сотрудника покажет эти статусы техническим кодом: " + ", ".join(
        missing
    )

    extra = sorted(set(labels) - server)
    assert not extra, "в словаре карточки есть статусы, которых у сервера нет: " + ", ".join(extra)

    for code, label in sorted(labels.items()):
        assert label != code, f"подпись {code} совпадает с кодом"
        assert re.search(r"[А-Яа-яЁё]", label), f"подпись {code} не по-русски: {label!r}"
