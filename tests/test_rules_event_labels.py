"""Сторож: каждое событие конструктора правил подписано по-русски (срез-159).

ЗАЧЕМ. В конструкторе правил человек выбирает событие-спусковой крючок. Список
приходит с сервера кодами (`WorkPermitIssued`, `approval.started`), а подписи
живут на витрине отдельным словарём. Если подписи нет, экран показывает сам
код латиницей: выбрать можно, понять нельзя.

Так и было с семью событиями из тридцати трёх: наряд-допуск, три шага
согласования, статус в ЭДО, лента изменений клиента и обращение к устаревшему
API. Словарь пополняли руками, а сверять его было нечем — ровно тот же класс,
что закрывали сторожа словарей происшествий и проверок (срез-150) и ролей
получателей (срез-148).

КАК ПРОВЕРЯЕТСЯ. Каталог берётся у сервера (`event_catalog()`), подписи
читаются из исходника витрины. Проверка идёт в обе стороны: нет подписи —
человек увидит код; есть лишняя — словарь оброс мёртвыми строками и
подсказывает, что событие ещё предлагается, хотя его убрали.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.rules_engine.catalog import event_catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
VOCAB = REPO_ROOT / "frontend" / "src" / "pages" / "rules" / "rulesVocab.ts"


def _event_labels() -> dict[str, str]:
    """Словарь `EVENT_LABELS` из исходника витрины."""

    text = VOCAB.read_text(encoding="utf-8")
    assert "export const EVENT_LABELS" in text, "словарь подписей событий переехал"
    block = text.split("export const EVENT_LABELS", 1)[1].split("};", 1)[0]
    pairs = re.findall(r'^\s*"?([A-Za-z_][A-Za-z0-9_.]*)"?:\s*"([^"]+)"', block, re.M)
    return dict(pairs)


def test_словарь_подписей_читается() -> None:
    labels = _event_labels()
    assert len(labels) > 25, f"подписей найдено всего {len(labels)} — чтение словаря сломалось"
    assert labels.get("IncidentCreated") == "Создан инцидент"


def test_каждое_событие_конструктора_подписано_по_русски() -> None:
    labels = _event_labels()
    offered = {item["event_type"] for item in event_catalog()}

    missing = sorted(offered - set(labels))
    assert not missing, (
        "конструктор правил покажет эти события техническим кодом латиницей — "
        "человек не поймёт, что выбирает:\n" + "\n".join(f"  {code}" for code in missing)
    )

    extra = sorted(set(labels) - offered)
    assert not extra, (
        "в словаре витрины остались подписи событий, которых конструктор уже не "
        "предлагает:\n" + "\n".join(f"  {code}" for code in extra)
    )

    for code in sorted(offered):
        label = labels[code]
        assert label != code, f"подпись {code} совпадает с кодом"
        assert re.search(r"[А-Яа-яЁё]", label), f"подпись {code} написана не по-русски: {label!r}"
