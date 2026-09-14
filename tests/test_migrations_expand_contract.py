"""OPS-74 (Доп. №4 разд. 74.2): миграции на живой системе — expand-contract.

ТЗ прямо называет правило: «Только additive-миграции по умолчанию… Expand-contract
паттерн: сначала добавить новое (expand), выкатить код, потом удалить старое
отдельным шагом (contract) — а не всё сразу… Во время деплоя одновременно
работают старый и новый код — схема должна поддерживать оба».

**Что нашла сверка.** Сторож миграций в репозитории есть и мощный
(`test_migrations_comprehensive_safety.py`, классы A1–A5: enum, GIN, кросс-ветковые
зависимости), но **правила additive среди его проверок НЕТ**. То есть требование
ТЗ было записано и ничем не подкреплено: миграция, удаляющая колонку в том же
шаге, где данные из неё переехали, проходила молча — а во время раската старый
код продолжает читать удалённую колонку.

## Что именно ловится и почему только это

Ловятся ``drop_table`` и ``drop_column`` в ``upgrade()``. Они однозначно ломают
старый код: колонки или таблицы больше нет, читать нечего.

НЕ ловятся:

* те же операции в ``downgrade()`` — там удаление это обратная операция к
  добавлению, то есть норма по построению;
* ``drop_constraint`` — снимает гарантию, но читать данные не мешает;
* ``alter_column`` — бывает и безопасным (снять NOT NULL), и опасным (сузить
  тип). Ловить его целиком значило бы получить 25 срабатываний, половина из
  которых ложные, — а сторож, который кричит всегда, перестают читать.

Эти границы названы здесь, а не умолчаны: «мы это не проверяем» и «мы это
проверили» — разные утверждения.

## Как объявить осознанный contract

Модуль миграции объявляет две константы::

    EXPAND_CONTRACT_STEP = "contract"
    EXPAND_CONTRACT_REASON = "почему удалять безопасно ИМЕННО СЕЙЧАС"

Причина обязательна и не может быть отпиской: «шаг contract» без объяснения,
почему у таблицы не осталось ни писателей, ни читателей, — это то же самое
удаление вслепую, только с ярлыком.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "backend/app/migrations/versions"

#: Операции, однозначно ломающие СТАРЫЙ код во время раската.
DESTRUCTIVE_OPS = frozenset({"drop_table", "drop_column"})

#: Миграции, сделанные ДО правила и не являющиеся честным contract. Каждая — с
#: причиной. Список закрыт: новая разрушительная миграция сюда не дописывается
#: «чтобы позеленело», она объявляет себя contract или переделывается в два шага.
ACCEPTED_LEGACY: dict[str, str] = {
    "20250325_outbox_outbound_traffic.py": (
        "март 2025, до правила: колонка dedupe_key удаляется в том же шаге, где "
        "данные переехали в idempotency_key. Ровно тот случай, который правило "
        "запрещает — во время раската старый код читал бы удалённую колонку. "
        "Переписывать историческую миграцию опаснее, чем оставить её записанной: "
        "она давно применена на всех установках"
    ),
}


def _destructive_ops_in_upgrade(path: pathlib.Path) -> set[str]:
    """Разрушительные вызовы внутри ``upgrade()``.

    Разбор идёт по AST, а не по тексту: ``batch_alter_table`` вызывает те же
    ``drop_column`` на своём объекте, и поиск подстрокой не отличил бы upgrade
    от downgrade.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "upgrade"):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr in DESTRUCTIVE_OPS
            ):
                found.add(inner.func.attr)
    return found


def _module_constant(path: pathlib.Path, name: str) -> str | None:
    """Значение строковой константы модуля без импорта миграции."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                try:
                    value = ast.literal_eval(node.value)
                except ValueError:
                    return None
                return value if isinstance(value, str) else None
    return None


def _all_migrations() -> list[pathlib.Path]:
    return sorted(MIGRATIONS.glob("*.py"))


def _destructive_migrations() -> list[pathlib.Path]:
    return [p for p in _all_migrations() if _destructive_ops_in_upgrade(p)]


def test_каталог_миграций_на_месте() -> None:
    """Пустой каталог сделал бы весь набор зелёным по построению."""

    assert MIGRATIONS.is_dir()
    assert len(_all_migrations()) > 100


@pytest.mark.parametrize(
    "path", _destructive_migrations(), ids=lambda p: p.name
)
def test_разрушительная_миграция_объявлена_шагом_contract(path: pathlib.Path) -> None:
    """Удаление в ``upgrade`` допустимо только как осознанный шаг contract.

    Иначе во время раската старый код читает то, чего уже нет: схема обязана
    держать обе версии кода одновременно (разд. 74.2).
    """

    if path.name in ACCEPTED_LEGACY:
        pytest.skip("миграция до правила, записана в ACCEPTED_LEGACY с причиной")

    step = _module_constant(path, "EXPAND_CONTRACT_STEP")
    ops = sorted(_destructive_ops_in_upgrade(path))
    assert step == "contract", (
        f"{path.name}: в upgrade есть {ops}, но шаг не объявлен. Либо разнесите "
        f'на два выката (expand → код → contract), либо объявите '
        f'EXPAND_CONTRACT_STEP = "contract" с причиной.'
    )


@pytest.mark.parametrize(
    "path", _destructive_migrations(), ids=lambda p: p.name
)
def test_у_шага_contract_названа_причина(path: pathlib.Path) -> None:
    """«Шаг contract» без объяснения — то же удаление вслепую, только с ярлыком."""

    if path.name in ACCEPTED_LEGACY:
        pytest.skip("миграция до правила, записана в ACCEPTED_LEGACY с причиной")

    reason = _module_constant(path, "EXPAND_CONTRACT_REASON")
    assert reason and reason.strip(), (
        f"{path.name}: объявлен contract, но не сказано, почему удалять "
        f"безопасно именно сейчас"
    )


class TestСписокДолгаНеПротух:
    """Обратная половина: список принятого долга обязан отражать правду."""

    @pytest.mark.parametrize("name", sorted(ACCEPTED_LEGACY), ids=lambda n: n)
    def test_запись_долга_указывает_на_существующую_миграцию(self, name: str) -> None:
        assert (MIGRATIONS / name).exists(), name

    @pytest.mark.parametrize("name", sorted(ACCEPTED_LEGACY), ids=lambda n: n)
    def test_запись_долга_всё_ещё_разрушительна(self, name: str) -> None:
        """Починили миграцию — запись обязана уйти, иначе список станет
        кладбищем неверных строк (тот же довод, что у реестра UX-долга)."""

        assert _destructive_ops_in_upgrade(MIGRATIONS / name), name

    @pytest.mark.parametrize("name", sorted(ACCEPTED_LEGACY), ids=lambda n: n)
    def test_у_записи_долга_есть_причина(self, name: str) -> None:
        assert ACCEPTED_LEGACY[name].strip(), name

    @pytest.mark.parametrize("name", sorted(ACCEPTED_LEGACY), ids=lambda n: n)
    def test_объявленный_contract_не_числится_долгом(self, name: str) -> None:
        """Одно из двух: либо миграция объявила contract, либо она в долге."""

        assert _module_constant(MIGRATIONS / name, "EXPAND_CONTRACT_STEP") != "contract", (
            f"{name}: миграция объявила contract — уберите её из ACCEPTED_LEGACY"
        )


# ---------------------------------------------------------------------------
# СРЕЗ-184 (OPS-74 разд. 74.3): откат должен быть возможен, а не обещан.
# ---------------------------------------------------------------------------
#
# Строка матрицы держала в остатке «SLA отката» с пометкой «это процесс, а не
# код». Половина этого — действительно процесс (за сколько минут дежурный
# принимает решение). Но вторая половина проверяется кодом и без неё SLA
# бессмыслен: у разрушительной миграции обязан быть РАБОЧИЙ ``downgrade``.
#
# Пустой ``downgrade`` у миграции, удаляющей таблицу, означает, что откат
# невозможен в принципе: данных уже нет и вернуть их нечем. Обещать при этом
# «откатимся за N минут» — то же самое, что пустой адаптер, рапортующий об
# успешной отправке.
#
# Проверяются ТОЛЬКО разрушительные миграции. Требовать содержательный
# ``downgrade`` от каждой — значит получить два десятка ложных срабатываний на
# слияниях веток и правках данных, а сторож, который кричит всегда, перестают
# читать.


def _downgrade_is_empty(path: pathlib.Path) -> bool:
    """Пуст ли ``downgrade``: только ``pass`` и/или строка описания."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "downgrade":
            continue
        meaningful = [
            child
            for child in node.body
            if not (isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant))
            and not isinstance(child, ast.Pass)
        ]
        return not meaningful
    return True  # downgrade нет вовсе — откатить нечем


@pytest.mark.parametrize("path", _destructive_migrations(), ids=lambda p: p.name)
def test_у_разрушительной_миграции_есть_рабочий_откат(path: pathlib.Path) -> None:
    """SLA отката без работающего downgrade — обещание, а не свойство системы."""

    if path.name in ACCEPTED_LEGACY:
        pytest.skip("миграция до правила, записана в ACCEPTED_LEGACY с причиной")

    ops = sorted(_destructive_ops_in_upgrade(path))
    assert not _downgrade_is_empty(path), (
        f"{path.name}: в upgrade есть {ops}, а downgrade пуст — откатить выкат "
        f"нечем. Либо напишите обратную операцию, либо разнесите на expand и "
        f"contract так, чтобы откатывался каждый шаг по отдельности."
    )
