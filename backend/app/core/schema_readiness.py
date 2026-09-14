"""Готов ли ЭТОТ экземпляр принимать трафик по состоянию схемы (OPS-74, разд. 74.1).

ЧТО БЫЛО. ``/health/ready`` спрашивал, отвечают ли Postgres, Redis и хранилище
файлов. Про СХЕМУ не спрашивал ничего. На раскате без простоя это означает
следующее: новый экземпляр поднимается, его миграции ещё не накатаны, база
отвечает на ping — и экземпляр рапортует «готов». Балансировщик переводит на
него трафик, и живые пользователи получают ошибки на колонках, которых в базе
ещё нет.

Требование ТЗ называется health-gated rollout: «выкатывать следующую порцию
только после того, как предыдущая ответила, что здорова». Здоровье без сверки
схемы — это не здоровье.

ПРАВИЛО, КОТОРОЕ ЗДЕСЬ ЗАПИСАНО, и почему именно оно

Правило НЕсимметрично, и это главное:

* **код впереди базы — НЕ готов.** Мои миграции ещё не применены; я знаю про
  таблицы и колонки, которых в базе нет.
* **база впереди кода — ГОТОВ.** Это нормальное состояние раската по
  expand-contract: сначала накатывается добавляющая миграция, потом постепенно
  выкатывается код. Старый экземпляр обязан продолжать работать против новой
  схемы — ровно это и стережёт ``tests/test_migrations_expand_contract.py``.

Симметричное правило («любое расхождение — не готов») выглядит строже, но
делает раскат без простоя невозможным: в момент между накатом миграции и
выкаткой кода НИ ОДИН экземпляр не был бы готов, и сервис лёг бы целиком.

* **ревизия базы неизвестна коду — НЕ готов.** База ушла вперёд на ревизию из
  будущего: это откат кода на версию, которая про неё не знает. Продолжать
  опасно.

ЧЕГО НЕТ В БАЗЕ ВООБЩЕ. Таблицы ``alembic_version`` может не быть: так выглядит
обычный прогон тестов (схема строится из моделей, а не миграциями) и чистая
разработка. В production/staging это означает «миграции не запускались ни разу»
и потому НЕ готов; в development/test — готов с пометкой ``unknown``. Тот же
приём, что у сторожа SSRF: строгость зависит от окружения, а не от удачи.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Где живут миграции (alembic.ini лежит рядом с versions/).
_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

STATE_OK = "ok"
STATE_PENDING = "pending"
STATE_UNKNOWN_REVISION = "unknown_revision"
STATE_NEVER_MIGRATED = "never_migrated"
STATE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SchemaState:
    """Состояние схемы глазами этого экземпляра."""

    state: str
    ready: bool
    db_revisions: tuple[str, ...] = ()
    code_heads: tuple[str, ...] = ()
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"state": self.state, "ready": self.ready}
        if self.db_revisions:
            payload["db_revision"] = list(self.db_revisions)
        if self.code_heads:
            payload["code_head"] = list(self.code_heads)
        if self.detail:
            payload["detail"] = self.detail
        return payload


@lru_cache(maxsize=1)
def _script_directory():
    from alembic.config import Config  # noqa: PLC0415 - тяжёлый импорт
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config)


@lru_cache(maxsize=1)
def code_heads() -> tuple[str, ...]:
    """Головные ревизии, которые знает ЭТОТ код."""

    return tuple(sorted(_script_directory().get_heads()))


@lru_cache(maxsize=1)
def known_revisions() -> frozenset[str]:
    """Все ревизии, о которых код вообще слышал."""

    return frozenset(script.revision for script in _script_directory().walk_revisions())


def evaluate(db_revisions: tuple[str, ...] | None, *, app_env: str) -> SchemaState:
    """Вердикт по ревизиям базы. Вынесено отдельно, чтобы проверять без базы."""

    strict = app_env in ("production", "staging")
    heads = code_heads()

    if db_revisions is None:
        return SchemaState(
            state=STATE_NEVER_MIGRATED,
            ready=not strict,
            code_heads=heads,
            detail=(
                "таблицы alembic_version нет — миграции не запускались ни разу"
                if strict
                else "таблицы alembic_version нет; для development/test это норма"
            ),
        )

    unknown = tuple(rev for rev in db_revisions if rev not in known_revisions())
    if unknown:
        return SchemaState(
            state=STATE_UNKNOWN_REVISION,
            ready=False,
            db_revisions=db_revisions,
            code_heads=heads,
            detail=(
                f"база стоит на ревизии {', '.join(unknown)}, которой этот код не знает: "
                "похоже на откат кода назад при уже накатанной базе"
            ),
        )

    missing = tuple(head for head in heads if head not in db_revisions)
    if missing:
        return SchemaState(
            state=STATE_PENDING,
            ready=False,
            db_revisions=db_revisions,
            code_heads=heads,
            detail=(
                f"миграции {', '.join(missing)} ещё не накатаны — "
                "экземпляр знает про таблицы и колонки, которых в базе нет"
            ),
        )

    # База может стоять ВПЕРЕДИ кода: так и выглядит expand-фаза раската.
    # Это штатное состояние, а не ошибка.
    ahead = tuple(rev for rev in db_revisions if rev not in heads)
    return SchemaState(
        state=STATE_OK,
        ready=True,
        db_revisions=db_revisions,
        code_heads=heads,
        detail=("база впереди кода (expand-фаза раската) — совместимо" if ahead else ""),
    )


async def read_db_revisions(connection) -> tuple[str, ...] | None:
    """Ревизии из ``alembic_version``. ``None`` — таблицы нет."""

    result = await connection.execute(text("SELECT version_num FROM alembic_version"))
    return tuple(sorted(row[0] for row in result.fetchall()))


async def check(open_connection, *, app_env: str) -> SchemaState:
    """Состояние схемы: прочитать ревизии и вынести вердикт.

    ``open_connection`` — то, что даёт соединение или сессию в ``async with``
    (в бою ``engine.connect``, в тестах — подсунутая фабрика сессий).

    Любая ошибка чтения — это ``unavailable`` и НЕ готов в строгих окружениях:
    «не смог проверить» и «проверил, всё хорошо» — разные утверждения, и
    подменять одно другим на раскате особенно дорого.
    """

    try:
        async with open_connection() as connection:
            try:
                revisions = await read_db_revisions(connection)
            except Exception:  # таблицы нет — это отдельный, ожидаемый случай
                revisions = None
    except Exception as exc:
        logger.warning("schema_readiness.unavailable", exc_info=True)
        strict = app_env in ("production", "staging")
        return SchemaState(
            state=STATE_UNAVAILABLE,
            ready=not strict,
            code_heads=code_heads(),
            detail=f"не удалось прочитать состояние схемы: {type(exc).__name__}",
        )

    return evaluate(revisions, app_env=app_env)


__all__ = [
    "STATE_NEVER_MIGRATED",
    "STATE_OK",
    "STATE_PENDING",
    "STATE_UNAVAILABLE",
    "STATE_UNKNOWN_REVISION",
    "SchemaState",
    "check",
    "code_heads",
    "evaluate",
    "known_revisions",
]
