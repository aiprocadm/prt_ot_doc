"""Сторож: экран уведомлений подписывает всё, что шлёт сервер (срез-178).

ЧТО БЫЛО. Экран уведомлений показывал четыре поля так, как они записаны в
коде: вид письма (`TrainingDueSoon`), канал (`inapp`), важность (`medium`) и
состояние (`queued`). Человек видел латиницу и догадывался сам. Фильтр по виду
предлагал те же коды, а подсказка «Типы: …» перечисляла их же.

Это тот же класс, что срезы 150 (виды происшествий и проверок), 159 (события
конструктора правил) и 160 (статусы выдачи СИЗ): список ведётся руками, а
сверять его нечем.

КАК ПРОВЕРЯЕТСЯ. Словари читаются из исходника витрины, составы сверяются с
перечислениями сервера в обе стороны: пропущенное значение снова покажется
кодом, лишнее означало бы, что словарь оброс мёртвыми строками. Подпись обязана
отличаться от кода и быть по-русски.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.notifications import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VOCAB = REPO_ROOT / "frontend" / "src" / "pages" / "notifications" / "notificationsVocab.ts"


def _labels(name: str) -> dict[str, str]:
    text = VOCAB.read_text(encoding="utf-8")
    assert f"export const {name}" in text, f"словарь {name} исчез с витрины"
    block = text.split(f"export const {name}", 1)[1].split("};", 1)[0]
    return dict(re.findall(r'^\s*"?([A-Za-z_][A-Za-z0-9_]*)"?:\s*"([^"]+)"', block, re.M))


CASES = [
    ("NOTIFICATION_TYPE_LABELS", {item.value for item in NotificationType}, "вид уведомления"),
    ("NOTIFICATION_CHANNEL_LABELS", {item.value for item in NotificationChannel}, "канал"),
    ("NOTIFICATION_STATUS_LABELS", {item.value for item in NotificationStatus}, "состояние"),
    ("NOTIFICATION_PRIORITY_LABELS", {item.value for item in NotificationPriority}, "важность"),
]


def test_словари_читаются() -> None:
    labels = _labels("NOTIFICATION_TYPE_LABELS")
    assert len(labels) > 20, f"подписей видов найдено всего {len(labels)} — чтение сломалось"
    assert labels.get("TrainingOverdue") == "Обучение просрочено"


@pytest.mark.parametrize("name,server,human", CASES)
def test_состав_совпадает_с_сервером(name: str, server: set[str], human: str) -> None:
    labels = _labels(name)

    missing = sorted(server - set(labels))
    assert not missing, f"экран покажет эти значения ({human}) техническим кодом: " + ", ".join(
        missing
    )

    extra = sorted(set(labels) - server)
    assert not extra, f"в словаре ({human}) есть значения, которых сервер не шлёт: " + ", ".join(
        extra
    )


@pytest.mark.parametrize("name,server,human", CASES)
def test_подписи_по_русски_и_не_повторяют_код(name: str, server: set[str], human: str) -> None:
    for code, label in sorted(_labels(name).items()):
        assert label != code, f"подпись {code} ({human}) совпадает с кодом"
        assert re.search(r"[А-Яа-яЁё]", label), f"подпись {code} ({human}) не по-русски: {label!r}"


def test_экран_зовёт_подписи_а_не_печатает_коды() -> None:
    page = (VOCAB.parent / "NotificationsPage.tsx").read_text(encoding="utf-8")
    for raw in ("{item.type}", "{item.channel}", "{item.priority}", "{item.status}"):
        assert (
            raw not in page
        ), f"на экране снова печатается сырой код {raw} — человек увидит латиницу"
