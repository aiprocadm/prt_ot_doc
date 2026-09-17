"""Сторож: обязательство по резервным копиям считается, а не обещается (OPS-72, срез-188).

ЧТО БЫЛО. Акт офбординга честно перечислял, что удалено из живой базы и из
хранилища файлов. Про резервные копии — ничего, и строка матрицы держала
остаток «удаление из бэкапов (организационная политика)». Клиент ушёл, акт
подписан, а копии за последние недели содержат всё, и никто не знает, когда
это перестанет быть правдой.

ЧЕГО ЗДЕСЬ НЕТ И НЕ БУДЕТ. Кода, «удаляющего данные из резервных копий».
Выборочное удаление строки из копии невозможно без того, чтобы сделать копию
непригодной для восстановления. Функция с таким именем была бы враньём — ровно
тот класс, за который платформа уже платила пустыми адаптерами. Отдельный тест
держит это свойство: в модуле нет ничего похожего на «удалить из копии».

ЧТО ЕСТЬ. Копии вытесняются ротацией, значит у обязательства есть вычислимая
дата. Она пишется в акт СРАЗУ, и просрочка видна.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_backup_retention_obligation.py -v``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.offboarding import backup_retention as br

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _settings(days: int | None = 35) -> SimpleNamespace:
    return SimpleNamespace(backup_retention_days=days)


def _record(*, purged_at: datetime, block: dict | None, status: str = "purged"):
    act = {"executed_at": purged_at.isoformat()}
    if block is not None:
        act["backup_purge"] = block
    return SimpleNamespace(tenant_id="t-1", tenant_slug="romashka", status=status, purge_act=act)


def test_дата_считается_от_дня_удаления_и_срока_хранения() -> None:
    block = br.build_obligation(purged_at=NOW, settings=_settings(35))
    assert block["retention_days"] == 35
    assert block["due_at"] == (NOW + timedelta(days=35)).isoformat()
    assert block["confirmed_at"] is None


def test_оговорка_объясняет_почему_нельзя_удалить_сразу() -> None:
    """Акт читает юрист, а не инженер: причина должна быть в самом акте."""

    block = br.build_obligation(purged_at=NOW, settings=_settings())
    assert "невозможно" in block["note"]
    assert "ротацией" in block["note"]


def test_срок_хранения_из_настройки_а_не_из_догадки() -> None:
    assert br.retention_days(_settings(7)) == 7
    assert br.retention_days(_settings(None)) == br.DEFAULT_RETENTION_DAYS
    assert br.retention_days(SimpleNamespace()) == br.DEFAULT_RETENTION_DAYS
    # Мусор в настройке не должен молча превращаться в ноль дней.
    assert br.retention_days(SimpleNamespace(backup_retention_days="скоро")) == (
        br.DEFAULT_RETENTION_DAYS
    )
    assert br.retention_days(SimpleNamespace(backup_retention_days=0)) == 1


class TestСостояниеОбязательства:
    def test_срок_не_наступил(self) -> None:
        block = br.build_obligation(purged_at=NOW, settings=_settings(35))
        assert br.obligation_state(block, now=NOW + timedelta(days=10)) == br.STATE_PENDING

    def test_срок_наступил(self) -> None:
        block = br.build_obligation(purged_at=NOW, settings=_settings(35))
        assert br.obligation_state(block, now=NOW + timedelta(days=36)) == br.STATE_DUE

    def test_просрочено(self) -> None:
        """Забытое обязательство обязано всплыть само, а не ждать проверки."""

        block = br.build_obligation(purged_at=NOW, settings=_settings(35))
        late = NOW + timedelta(days=35 + br.OVERDUE_GRACE_DAYS + 1)
        assert br.obligation_state(block, now=late) == br.STATE_OVERDUE

    def test_подтверждённое_закрыто(self) -> None:
        block = br.build_obligation(purged_at=NOW, settings=_settings(1))
        block["confirmed_at"] = (NOW + timedelta(days=2)).isoformat()
        block["confirmed_by"] = "Дежурный"
        assert br.obligation_state(block, now=NOW + timedelta(days=99)) == br.STATE_CLOSED

    def test_акт_без_блока_считается_просроченным(self) -> None:
        """Старый акт не знает срока. Молчать об этом нельзя: обязательство
        просто исчезло бы из виду, а оно есть."""

        assert br.obligation_state({}, now=NOW) == br.STATE_OVERDUE


def test_в_выдаче_только_то_на_что_надо_смотреть() -> None:
    """Список, в котором шумят все строки подряд, перестают читать."""

    pending = _record(
        purged_at=NOW, block=br.build_obligation(purged_at=NOW, settings=_settings(35))
    )
    overdue = _record(
        purged_at=NOW - timedelta(days=100),
        block=br.build_obligation(purged_at=NOW - timedelta(days=100), settings=_settings(35)),
    )
    report = br.summarize(br.collect([pending, overdue], now=NOW))
    assert report["total"] == 2
    assert report["pending"] == 1
    assert report["overdue"] == 1
    assert len(report["items"]) == 1


def test_неудалённые_арендаторы_не_попадают_в_обязательства() -> None:
    active = _record(purged_at=NOW, block=None, status="grace")
    assert br.collect([active], now=NOW) == []


def test_модуль_не_делает_вид_что_удаляет_из_копий() -> None:
    """Главное свойство строки: честность формулировок.

    Если когда-нибудь здесь появится функция «удалить из резервной копии», это
    будет враньём — выборочно вычистить строку из копии нельзя. Тест держит
    границу словами, а не намерением.
    """

    names = dir(br)
    forbidden = [n for n in names if "delete" in n.lower() or "purge_backup" in n.lower()]
    assert not forbidden, f"модуль обещает удаление из копий: {forbidden}"
