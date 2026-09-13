"""Сторож: экран интеграций понимает статусы исходящих доставок (срез-161).

ЧТО БЫЛО. Ручка `/admin/outbox` отдаёт статус доставки ПРОПИСНЫМИ — это
значения перечисления ``OutboxStatus`` (`PENDING`, `IN_PROGRESS`, `SENT`,
`FAILED`, `DEAD`). Экран интеграций сравнивал их со строчными строками, и не
совпадало НИЧЕГО:

* фильтр по статусу опустошал таблицу при любом выборе;
* счётчики «сбоев доставки» и «доставлено» показывали ноль всегда;
* кнопка «Повторить» у сбойной доставки не появлялась никогда;
* значок статуса показывал `FAILED` серым вместо «Сбой» красным.

Соседний список событий (``OutboxEventStatus``) наоборот строчный — поэтому
регистр приводится к одному виду на входе, а не правится сравнениями по
одному.

КАК ПРОВЕРЯЕТСЯ. Значения выбора в фильтре читаются из исходника экрана и
сверяются с перечислением сервера без учёта регистра: лишнего быть не должно
(выбор, которого сервер не знает, — пустая таблица), и каждый статус обязан
иметь русскую подпись в общем значке, иначе человек снова увидит код.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.models import OutboxStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "frontend" / "src" / "pages" / "integrations" / "IntegrationsPage.tsx"
BADGE = REPO_ROOT / "frontend" / "src" / "components" / "common" / "StatusBadge.tsx"


def _filter_values() -> set[str]:
    text = PAGE.read_text(encoding="utf-8")
    block = text.split("value={statusFilter}", 1)[1].split("</select>", 1)[0]
    values = set(re.findall(r'<option value="([a-z_]+)"', block))
    return values - {"all"}


def _badge_labels() -> dict[str, str]:
    text = BADGE.read_text(encoding="utf-8")
    block = text.split("const statusLabelsRu", 1)[1].split("};", 1)[0]
    return dict(re.findall(r"^\s*([a-z_]+):\s*\"([^\"]+)\"", block, re.M))


def test_исходники_читаются() -> None:
    assert "pending" in _filter_values(), "чтение значений фильтра сломалось"
    assert _badge_labels().get("failed") == "Сбой", "чтение подписей значка сломалось"


def test_фильтр_предлагает_только_известные_серверу_статусы() -> None:
    server = {status.value.lower() for status in OutboxStatus}
    unknown = sorted(_filter_values() - server)
    assert not unknown, (
        "фильтр предлагает статусы, которых сервер не отдаёт — выбор опустошит "
        "таблицу: " + ", ".join(unknown)
    )


def test_каждый_статус_доставки_подписан_по_русски() -> None:
    labels = _badge_labels()
    missing = sorted(
        status.value.lower() for status in OutboxStatus if status.value.lower() not in labels
    )
    assert not missing, "значок покажет эти статусы кодом латиницей: " + ", ".join(missing)


def test_экран_приводит_регистр_статуса() -> None:
    """Без приведения регистра сравнения снова разойдутся с сервером.

    Сравнения со СТРОЧНЫМИ в файле остаются — они про соседний список
    событий, где сервер и правда отдаёт строчные. Поэтому проверяем не их
    отсутствие, а что каждое место работы со статусом ДОСТАВКИ идёт через
    приведение регистра: фильтр, оба счётчика и кнопка повтора.
    """

    text = PAGE.read_text(encoding="utf-8")
    assert text.count("deliveryStatus(item.status)") >= 4, (
        "приведение регистра статуса доставки применяется не везде: "
        f"найдено {text.count('deliveryStatus(item.status)')} мест из четырёх "
        "(фильтр, счётчик сбоев, счётчик доставленных, кнопка повтора)"
    )
