"""SEC-66: слова на экране ПДн и словари сервера — один состав.

ЗАЧЕМ. Срез-209 завёл экран прав субъекта и печатал на нём служебные коды:
человек видел «consent» и «active» латиницей. Сторож
`tests/test_frontend_raw_status_prints.py` это поймал, коды заменены словами.

Но словарь на витрине — это КОПИЯ серверного перечня, а копии расходятся. Если
сервер заведёт новое основание обработки, экран молча покажет его кодом — ровно
тот дефект, который только что чинили. Поэтому составы сверяются здесь.

Разбор идёт по ТЕКСТУ витрины (там нет иного способа), поэтому первым делом
проверяется САМ РАЗБОР: если он перестанет находить словарь, тест скажет об
этом, а не притворится зелёным.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.privacy_consents import PDN_CONSENT_STATUSES, PDN_LEGAL_BASES

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREEN = REPO_ROOT / "frontend" / "src" / "pages" / "privacy" / "PrivacySubjectPage.tsx"


def _keys_of(dictionary_name: str) -> set[str]:
    """Ключи словаря витрины: имя → { ключ: "слово" }."""

    source = SCREEN.read_text(encoding="utf-8")
    match = re.search(
        rf"const {dictionary_name}: Record<string, string> = \{{(.*?)\n\}};",
        source,
        re.DOTALL,
    )
    assert match, f"на экране больше нет словаря {dictionary_name} — разбор потерял область"
    return set(re.findall(r"^\s*([a-z_]+):", match.group(1), re.MULTILINE))


def test_разбор_находит_оба_словаря() -> None:
    # Самопроверка разбора: пустой результат означал бы зелёный тест ни о чём.
    assert _keys_of("LEGAL_BASIS_TITLES")
    assert _keys_of("CONSENT_STATUS_TITLES")


def test_основания_обработки_названы_все() -> None:
    assert _keys_of("LEGAL_BASIS_TITLES") == set(PDN_LEGAL_BASES), (
        "состав оснований обработки на экране разошёлся с сервером: человек увидит код "
        "латиницей вместо слова"
    )


def test_состояния_согласия_названы_все() -> None:
    assert _keys_of("CONSENT_STATUS_TITLES") == set(
        PDN_CONSENT_STATUSES
    ), "состав состояний согласия на экране разошёлся с сервером"
