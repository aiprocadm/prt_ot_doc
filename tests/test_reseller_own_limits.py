"""Свои лимиты и свой расход (BIZ-52 срез-15, Доп. №1 разд. 52.4)."""

from __future__ import annotations

from app.domains.reseller.own_limits import BYTES_IN_MB, LimitLine, build_limit_lines


def _lines(**overrides):
    base = dict(
        max_doc_generations_per_month=100,
        max_storage_mb=10,
        monthly_edo_outgoing=50,
        max_parallel_jobs=4,
        doc_generations_used=80,
        storage_bytes_used=5 * BYTES_IN_MB,
    )
    base.update(overrides)
    return {line.code: line for line in build_limit_lines(**base)}


def test_рядом_с_лимитом_стоит_расход():
    # «10 000 документов в месяц» не отвечает на вопрос «хватит ли до конца
    # месяца»; отвечает пара «использовано 80 из 100».
    line = _lines()["doc_generations"]

    assert line.limit == 100
    assert line.used == 80
    assert line.remaining == 20


def test_хранилище_переводится_в_одни_единицы():
    # Квота хранится в мегабайтах, расход считается в байтах: без приведения
    # «использовано 5 из 10» означало бы 5 байт из 10 мегабайт.
    line = _lines()["storage"]

    assert line.limit == 10 * BYTES_IN_MB
    assert line.used == 5 * BYTES_IN_MB


def test_остаток_не_уходит_в_минус():
    # Перерасход бывает: гейт срабатывает не мгновенно. «Осталось −40» человек
    # прочитает как ошибку расчёта.
    line = _lines(doc_generations_used=140)["doc_generations"]

    assert line.remaining == 0
    assert line.exhausted is True


def test_несчитаемый_расход_не_показывается_нулём():
    # Счётчик ЭДО не увеличивает никто (провайдер отправки не реализован).
    # Ноль означал бы «ЭДО не пользуются» вместо «мы это не считаем».
    line = _lines()["edo_outgoing"]

    assert line.limit == 50
    assert line.used is None
    assert line.measured is False


def test_одновременность_не_путается_с_месячным_расходом():
    # `max_parallel_jobs` — предел ОДНОВРЕМЕННОСТИ; величины «использовано за
    # период» рядом с ним нет, и выдумывать её нельзя.
    line = _lines()["parallel_jobs"]

    assert line.limit == 4
    assert line.used is None


def test_неизвестный_остаток_это_не_исчерпание():
    # `remaining is None` означает «неизвестно»; путать с «всё израсходовано»
    # нельзя — иначе кабинет пугал бы партнёра красным без причины.
    line = _lines()["edo_outgoing"]

    assert line.remaining is None
    assert line.exhausted is False


def test_без_квот_пределов_нет():
    lines = _lines(
        max_doc_generations_per_month=None,
        max_storage_mb=None,
        monthly_edo_outgoing=None,
        max_parallel_jobs=None,
    )

    assert all(line.limit is None for line in lines.values())
    # Расход при этом продолжает считаться: он не зависит от наличия квоты.
    assert lines["doc_generations"].used == 80


def test_без_предела_остаток_неизвестен():
    line = _lines(max_doc_generations_per_month=None)["doc_generations"]

    assert line.remaining is None
    assert line.exhausted is False


def test_строки_идут_в_понятном_порядке():
    codes = [
        line.code
        for line in build_limit_lines(
            max_doc_generations_per_month=1,
            max_storage_mb=1,
            monthly_edo_outgoing=1,
            max_parallel_jobs=1,
            doc_generations_used=0,
            storage_bytes_used=0,
        )
    ]

    # Сначала то, что считается, потом то, что нет: иначе человек первым делом
    # видит прочерки и решает, что не работает ничего.
    assert codes == ["doc_generations", "storage", "edo_outgoing", "parallel_jobs"]


def test_у_каждой_строки_есть_единица_измерения():
    for line in _lines().values():
        assert isinstance(line, LimitLine)
        assert line.unit
