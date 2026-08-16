"""Импорт как источник сигналов (BIZ-51 срез-2, Доп. №1 разд. 51.2)."""

from __future__ import annotations

from datetime import date

from app.domains.managed_clients.change_feed import ClientChangeKind
from app.domains.managed_clients.import_signals import (
    MAX_SIGNALS_PER_BATCH,
    RowFact,
    signals_for_batch,
)

LOADED = date(2026, 8, 16)
COMPANY = "company-1"


def _person(action: str, **kwargs) -> RowFact:
    payload: dict = {
        "target": "persons",
        "action": action,
        "company_id": COMPANY,
        "title": "Иванов Иван",
        "entity_id": "p-1",
    }
    payload.update(kwargs)
    return RowFact(**payload)


def test_новая_строка_сотрудника_это_приём_на_работу():
    signals = signals_for_batch("persons", [_person("create")], applied_on=LOADED)

    assert [s.kind for s in signals] == [ClientChangeKind.EMPLOYEE_HIRED]
    assert signals[0].summary.startswith("Принят")


def test_дата_берётся_из_приёма_а_не_из_дня_загрузки():
    """Приняли в пятницу, загрузили в понедельник — сроки считаются от пятницы.

    Инструктаж и медосмотр привязаны к приёму; сдвиг даты на день загрузки
    тихо сдвинул бы и их сроки.
    """

    fact = _person("create", now={"hired_at": date(2026, 8, 10)})

    signals = signals_for_batch("persons", [fact], applied_on=LOADED)

    assert signals[0].happened_on == date(2026, 8, 10)


def test_без_даты_приёма_берётся_день_загрузки():
    signals = signals_for_batch("persons", [_person("create")], applied_on=LOADED)

    assert signals[0].happened_on == LOADED


def test_первая_загрузка_не_объявляет_перенос_данных_приёмом_на_работу():
    """Привезли штатку на 500 человек — это перенос, а не 500 приёмов.

    Самая дорогая ошибка этого среза: лента, в которую при первом же импорте
    падает весь штат клиента, обесценивается в тот же день.
    """

    facts = [_person("create", entity_id=f"p-{i}") for i in range(500)]

    signals = signals_for_batch(
        "persons", facts, applied_on=LOADED, initial_load_companies=[COMPANY]
    )

    assert signals == ()


def test_первичность_считается_по_каждой_компании_отдельно():
    # У аутсорсера много клиентов: первая загрузка по одному не должна глушить
    # сигналы по остальным.
    facts = [
        _person("create", company_id="company-new", entity_id="p-1"),
        _person("create", company_id="company-old", entity_id="p-2"),
    ]

    signals = signals_for_batch(
        "persons", facts, applied_on=LOADED, initial_load_companies=["company-new"]
    )

    assert [s.company_id for s in signals] == ["company-old"]


def test_увольнение_видно_по_смене_статуса():
    fact = _person(
        "update",
        before={"employment_status": "active"},
        now={"employment_status": "terminated"},
    )

    signals = signals_for_batch("persons", [fact], applied_on=LOADED)

    assert [s.kind for s in signals] == [ClientChangeKind.EMPLOYEE_LEFT]
    assert signals[0].summary.startswith("Уволен")


def test_уже_уволенный_повторным_увольнением_не_считается():
    # Иначе каждая перезагрузка того же файла плодила бы «уволен» заново.
    fact = _person(
        "update",
        before={"employment_status": "terminated"},
        now={"employment_status": "terminated"},
    )

    assert signals_for_batch("persons", [fact], applied_on=LOADED) == ()


def test_отсутствие_строки_в_файле_увольнением_НЕ_считается():
    """Файл почти никогда не полный — выгружают один цех.

    Правило «кого нет в файле, тот уволен» на загрузке списка сварщиков
    «уволило» бы весь остальной завод. Поэтому исчезнувших строк здесь нет
    вовсе: сигналы строятся только по тому, что в файле ЕСТЬ.
    """

    signals = signals_for_batch("persons", [], applied_on=LOADED)

    assert signals == ()


def test_смена_должности_это_перевод():
    fact = _person(
        "update",
        before={"position_id": "pos-1"},
        now={"position_id": "pos-2", "position_title": "Сварщик"},
    )

    signals = signals_for_batch("persons", [fact], applied_on=LOADED)

    assert [s.kind for s in signals] == [ClientChangeKind.EMPLOYEE_LEFT]
    assert signals[0].summary.startswith("Переведён")
    assert "Сварщик" in (signals[0].details or "")


def test_перевод_и_увольнение_это_один_вид_из_таблицы_тз():
    # В разд. 51.1 строка одна: «Уволен / переведён сотрудник». Разводить их на
    # два вида значило бы придумать девятый, которого в ТЗ нет.
    fired = _person(
        "update", before={"employment_status": "active"}, now={"employment_status": "terminated"}
    )
    moved = _person("update", before={"position_id": "a"}, now={"position_id": "b"})

    kinds = {
        signals_for_batch("persons", [fired], applied_on=LOADED)[0].kind,
        signals_for_batch("persons", [moved], applied_on=LOADED)[0].kind,
    }

    assert kinds == {ClientChangeKind.EMPLOYEE_LEFT}


def test_правка_телефона_изменением_у_клиента_не_считается():
    # Иначе лента наполнится опечатками и перестанет читаться.
    fact = _person("update", before={"phone": "+7 000"}, now={"phone": "+7 111"})

    assert signals_for_batch("persons", [fact], applied_on=LOADED) == ()


def test_новая_должность_и_новый_объект_дают_свои_виды():
    position = RowFact(
        target="positions", action="create", company_id=COMPANY, title="Слесарь", entity_id="x"
    )
    site = RowFact(
        target="sites", action="create", company_id=COMPANY, title="Цех №2", entity_id="y"
    )

    assert signals_for_batch("positions", [position], applied_on=LOADED)[0].kind is (
        ClientChangeKind.POSITION_ADDED
    )
    assert signals_for_batch("sites", [site], applied_on=LOADED)[0].kind is (
        ClientChangeKind.SITE_ADDED
    )


def test_переименование_должности_изменением_не_считается():
    # Набор обязательств от смены буквы в названии не меняется.
    fact = RowFact(
        target="positions", action="update", company_id=COMPANY, title="Слесарь-ремонтник"
    )

    assert signals_for_batch("positions", [fact], applied_on=LOADED) == ()


def test_цели_без_строки_в_таблице_тз_сигналов_не_дают():
    # Нормы СИЗ — тоже импорт, но в разд. 51.1 для них строки нет, а выдумывать
    # последствия за ТЗ нельзя.
    fact = RowFact(target="ppe_norms", action="create", company_id=COMPANY, title="Каска")

    assert signals_for_batch("ppe_norms", [fact], applied_on=LOADED) == ()


def test_строка_без_компании_пропускается():
    # Лента ведётся по клиенту; запись, которую не к кому привязать, — мусор.
    fact = _person("create", company_id=None)

    assert signals_for_batch("persons", [fact], applied_on=LOADED) == ()


def test_огромная_загрузка_не_делает_ленту_нечитаемой():
    facts = [_person("create", entity_id=f"p-{i}") for i in range(MAX_SIGNALS_PER_BATCH + 50)]

    signals = signals_for_batch("persons", facts, applied_on=LOADED)

    assert len(signals) == MAX_SIGNALS_PER_BATCH


def test_словарь_действий_совпадает_с_тем_что_пишет_импорт():
    """Сторож против молчаливо пустой ленты.

    Планировщик импорта говорит «create», а в строку партии ложится «created».
    На этом рассинхроне срез уже ломался: фильтр не совпадал ни с чем, и
    импорт исправно не порождал НИЧЕГО — без единой ошибки в логах. Если в
    импорте появится новое успешное действие или переименуют старое, тест
    покраснеет здесь, а не в проде тишиной.
    """

    import re
    from pathlib import Path

    from app.services.client_change_signals import ROW_ACTIONS

    source = Path(__import__("app.modules.imports.service", fromlist=["x"]).__file__).read_text(
        encoding="utf-8"
    )
    written = set(re.findall(r'action="([a-z]+)"', source))
    # Неуспешные строки сигналов не дают: у них нет записи, о которой сообщать.
    successful = written - {"failed", "skipped"}

    assert successful == set(ROW_ACTIONS), (
        f"импорт пишет {sorted(successful)}, а разбор ждёт {sorted(ROW_ACTIONS)}"
    )


def test_длинное_имя_обрезается_под_колонку_ленты():
    fact = _person("create", title="Ы" * 400)

    summary = signals_for_batch("persons", [fact], applied_on=LOADED)[0].summary

    # Обрезается хвост: вид изменения обязан читаться с первого слова.
    assert len(summary) <= 255
    assert summary.startswith("Принят:")
