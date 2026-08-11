"""BIZ-52 — виды арендатора объявлены одинаково на обеих сторонах (разд. 52.1).

Вид арендатора — это его УРОВЕНЬ в иерархии продажи платформы, и он нужен
и серверу (правила «кто кому может завести арендатора»), и форме в админке.
Разойдись списки — форма предложит вид, который сервер отвергнет 422-й, либо
наоборот: новый уровень появится на сервере и останется недоступен человеку.
Тот же приём, что стережёт числа UX-бюджета (BIZ-59).
"""

from __future__ import annotations

import pathlib
import re
import typing

from app.domains.reseller import RESELLER_KIND
from app.schemas.tenant import TenantKind

_TS_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "types"
    / "dto"
    / "tenants.ts"
)


def _python_kinds() -> set[str]:
    return set(typing.get_args(TenantKind))


def _frontend_kinds() -> set[str]:
    text = _TS_PATH.read_text(encoding="utf-8")
    match = re.search(r"TENANT_KINDS\s*=\s*\[(.*?)\]\s*as const", text, flags=re.DOTALL)
    assert match is not None, "не нашли объявление TENANT_KINDS во фронтенде"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def test_frontend_file_exists() -> None:
    """Без файла сверка «сходится» вхолостую — и мы этого не заметим."""

    assert _TS_PATH.exists(), f"нет {_TS_PATH}"


def test_kinds_match_on_both_sides() -> None:
    assert _python_kinds() == _frontend_kinds()


def test_reseller_kind_is_present() -> None:
    """Уровень партнёра обязан существовать в обоих списках: на нём стоит 52.1."""

    assert RESELLER_KIND in _python_kinds()
    assert RESELLER_KIND in _frontend_kinds()


def test_kinds_match_the_spec() -> None:
    """Состав видов зафиксирован: новый уровень — решение о продукте, а не правка строки.

    Три уровня ТЗ (владелец платформы / реселлер / клиент) держатся на том, что
    `reseller` ровно один. Появись рядом «суб-реселлер», правила иерархии
    придётся переписывать, и это должно быть видно в диффе теста.
    """

    assert _python_kinds() == {"customer", "branch", "contractor", "reseller"}
