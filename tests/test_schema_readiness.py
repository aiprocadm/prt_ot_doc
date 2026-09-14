"""Сторож: готовность к трафику учитывает состояние схемы (OPS-74, срез-184).

ЧТО БЫЛО. ``/health/ready`` спрашивал, отвечают ли Postgres, Redis и хранилище
файлов. Про схему — ничего. На раскате без простоя это значит вот что: новый
экземпляр поднялся, его миграции ещё не накатаны, база на ping отвечает — и
экземпляр рапортует «готов». Балансировщик переводит на него трафик, живые
пользователи получают ошибки на колонках, которых в базе нет.

Требование ТЗ (разд. 74.1) называется health-gated rollout: следующую порцию
выкатывают только после того, как предыдущая ответила, что здорова. Здоровье
без сверки схемы — не здоровье.

ГЛАВНОЕ, ЧТО ПРОВЕРЯЕТСЯ: правило НЕсимметрично. Код впереди базы — не готов.
База впереди кода — ГОТОВ, это штатная expand-фаза. Симметричное правило
выглядит строже, но делает раскат без простоя невозможным: между накатом
миграции и выкаткой кода не был бы готов НИ ОДИН экземпляр, и сервис лёг бы
целиком. Отдельный тест держит именно эту несимметричность.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_schema_readiness.py -v``.
"""

from __future__ import annotations

import pytest

from app.core import schema_readiness as sr


@pytest.fixture
def heads() -> tuple[str, ...]:
    return sr.code_heads()


def test_code_knows_its_own_heads(heads) -> None:
    """Опора всей проверки: ревизии читаются из самих миграций, а не из списка."""

    assert heads, "alembic не отдал ни одной головной ревизии"
    assert all(head in sr.known_revisions() for head in heads)


def test_schema_at_head_is_ready(heads) -> None:
    state = sr.evaluate(heads, app_env="production")
    assert state.ready
    assert state.state == sr.STATE_OK


def test_code_ahead_of_db_is_not_ready(heads) -> None:
    """Миграции не накатаны — экземпляр не должен получать трафик."""

    # База стоит на какой-то известной НЕголовной ревизии.
    older = next(rev for rev in sr.known_revisions() if rev not in heads)
    state = sr.evaluate((older,), app_env="production")
    assert not state.ready
    assert state.state == sr.STATE_PENDING
    assert "ещё не накатаны" in state.detail


def test_db_ahead_of_code_is_ready(heads) -> None:
    """Expand-фаза: база уже новее, старый код обязан продолжать работать.

    Если бы здесь стоял отказ, раскат без простоя был бы невозможен: в
    промежутке между миграцией и выкаткой кода готовых экземпляров не осталось
    бы вовсе.
    """

    older = next(rev for rev in sr.known_revisions() if rev not in heads)
    state = sr.evaluate((*heads, older), app_env="production")
    assert state.ready
    assert state.state == sr.STATE_OK


def test_unknown_revision_is_not_ready(heads) -> None:
    """База ушла на ревизию из будущего — это откат кода назад, продолжать нельзя."""

    state = sr.evaluate(("revision-from-the-future",), app_env="production")
    assert not state.ready
    assert state.state == sr.STATE_UNKNOWN_REVISION


def test_never_migrated_is_strict_in_production_and_lenient_in_dev() -> None:
    """Таблицы alembic_version нет: в бою это «миграции не запускались»,
    в разработке — обычное дело (схема строится из моделей)."""

    assert not sr.evaluate(None, app_env="production").ready
    assert not sr.evaluate(None, app_env="staging").ready
    assert sr.evaluate(None, app_env="development").ready
    assert sr.evaluate(None, app_env="test").ready


@pytest.mark.asyncio
async def test_unreadable_db_is_not_ready_in_production() -> None:
    """«Не смог проверить» и «проверил, всё хорошо» — разные утверждения."""

    def broken():
        raise RuntimeError("no database")

    state = await sr.check(broken, app_env="production")
    assert not state.ready
    assert state.state == sr.STATE_UNAVAILABLE
    assert sr.STATE_UNAVAILABLE in state.as_dict()["state"]


@pytest.mark.asyncio
async def test_unreadable_db_does_not_block_development() -> None:
    def broken():
        raise RuntimeError("no database")

    assert (await sr.check(broken, app_env="development")).ready
