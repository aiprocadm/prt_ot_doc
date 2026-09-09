"""Команда CLI либо делает дело, либо честно говорит, что не делает (срез-130).

ЗАЧЕМ. Пять команд печатали ``status: queued`` (или ``scheduled``) и выходили
с нулём, не поставив в очередь НИЧЕГО: ``export``, ``backup``, ``restore``,
``reindex``, ``projections rebuild``. Ложь была видна только в исходниках —
снаружи команда выглядела успешной. Оператор, собравший на них ночной скрипт,
получал зелёный отчёт о резервных копиях, которых не существует.

Хуже прочих были две последние: работа за ними ЕСТЬ (те же пересборки, что
крутит ночной тик), и человек, нажавший «переиндексировать» после массового
импорта, был уверен, что поиск обновлён.

ЧТО ПРОВЕРЯЕТСЯ. Список команд берётся из самого приложения, а не из памяти.
У каждой ровно два законных состояния: она делает работу либо честно отвечает
``not_implemented`` с причиной словами и НЕНУЛЕВЫМ кодом возврата. Список
ломается в обе стороны: новая команда без разбора — красный, исчезнувшая
строка реестра — тоже.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from app.cli.main import EXIT_NOT_IMPLEMENTED, cli

#: Команды, за которыми работы в продукте НЕТ. Значение — обязательные
#: аргументы вызова: без них Typer ругается на разбор, а не на суть.
NOT_IMPLEMENTED: dict[tuple[str, ...], list[str]] = {
    ("export",): ["--tenant", "demo"],
    ("backup",): [],
    ("restore",): [],
}

#: Команды, которые работу делают. Значение — поле ИТОГА, которое обязано
#: быть в ответе: «принято» итогом не является.
DOES_WORK: dict[tuple[str, ...], str] = {
    ("reindex",): "rebuilt",
    ("projections", "rebuild"): "rebuilt",
    ("health", "check"): "status",
    ("health", "release-readiness"): "status",
}

#: Команды, которые здесь не проверяются: им нужны файлы и шаблоны, и они уже
#: покрыты своими тестами (``tests/test_cli_main.py``). Названы поимённо,
#: чтобы новая команда не растворилась в пропуске.
COVERED_ELSEWHERE = {
    ("render",): "нужен шаблон и файл контекста — tests/test_cli_main.py",
    ("header",): "нужен шаблон — tests/test_cli_main.py",
    ("replace",): "нужен документ на диске — tests/test_cli_main.py",
    ("pipeline",): "ставит настоящую задачу в очередь — tests/test_cli_main.py",
}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _registered() -> set[tuple[str, ...]]:
    """Все команды приложения — из самого Typer, а не из памяти."""

    found: set[tuple[str, ...]] = set()
    for command in cli.registered_commands:
        found.add((command.name or command.callback.__name__,))
    for group in cli.registered_groups:
        for command in group.typer_instance.registered_commands:
            found.add((group.name, command.name or command.callback.__name__))
    return found


def test_каждая_команда_разобрана() -> None:
    """Новая команда обязана попасть в один из трёх списков осознанно."""

    classified = set(NOT_IMPLEMENTED) | set(DOES_WORK) | set(COVERED_ELSEWHERE)
    registered = _registered()

    missing = sorted(registered - classified)
    stale = sorted(classified - registered)
    assert missing == [], (
        "команда не разобрана — она делает работу или честно отказывает? " f"{missing}"
    )
    assert stale == [], f"в реестре есть команды, которых больше нет: {stale}"


@pytest.mark.parametrize("args", list(NOT_IMPLEMENTED))
def test_нереализованная_команда_не_притворяется_успешной(
    runner: CliRunner, args: tuple[str, ...]
) -> None:
    """Ноль на выходе — это «сделано». За этими командами делать нечего."""

    result = runner.invoke(cli, [*args, *NOT_IMPLEMENTED[args], "--json"])

    assert result.exit_code == EXIT_NOT_IMPLEMENTED, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "not_implemented"
    # Причина словами: «не реализовано» без указателя оставляет оператора
    # ровно там же, где он был.
    assert len(payload["reason"]) > 30, payload["reason"]


@pytest.mark.parametrize("args", list(DOES_WORK))
def test_работающая_команда_отвечает_итогом(runner: CliRunner, args: tuple[str, ...]) -> None:
    """Ответ содержит ИТОГ работы, а не слово «принято»."""

    result = runner.invoke(cli, [*args, "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert DOES_WORK[args] in payload, payload
    assert payload.get("status") != "queued", "«queued» без очереди — это и была ложь"


def test_пересборка_из_командной_строки_и_ночью_идут_одним_путём() -> None:
    """Вторая копия обхода арендаторов разошлась бы с ночной при первой правке."""

    import inspect

    from app.cli import main as cli_main

    source = inspect.getsource(cli_main)
    assert "rebuild_search_snapshot" in source
    assert "rebuild_read_model_snapshots" in source
    # Обхода арендаторов в CLI быть не должно — он один и живёт у тиков.
    assert "is_active.is_(True)" not in source


@pytest.mark.anyio
async def test_переиндексация_из_командной_строки_действительно_наполняет_снимок(
    sessionmaker, data_factory
) -> None:
    """Самое важное: команда СДЕЛАЛА работу, а не отчиталась о ней.

    Раньше человек, нажавший «переиндексировать» после массового импорта, был
    уверен, что поиск обновлён; на деле снимок оставался прежним.
    """

    from anyio import to_thread

    from app.modules.projections.models import SearchIndexEntry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="test", session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Срез-130", session=session
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Найдётся", session=session
        )
        await session.commit()
        tenant_id, person_id = str(tenant.id), str(person.id)

    # Команда зовёт `asyncio.run` внутри себя — запускаем её в отдельном
    # потоке, иначе цикл событий теста вложился бы сам в себя.
    result = await to_thread.run_sync(
        lambda: CliRunner().invoke(cli, ["reindex", "--tenant", "test", "--json"])
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["rebuilt"] >= 1

    from sqlalchemy import select

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(SearchIndexEntry).where(
                    SearchIndexEntry.tenant_id == tenant_id,
                    SearchIndexEntry.entity_id == person_id,
                )
            )
        ).scalar_one()
    assert "Найдётся" in (row.title or "")
