"""Regression guard: ``configure_mappers()`` must succeed across the full ORM graph.

Two mapped classes are named ``Inspection`` — ``app.models.checks.Inspection``
(table ``inspection``) and ``app.models.models.Inspection`` (table
``regulatory_inspection``) — and they share one declarative registry. A bare,
string-keyed ``relationship("Inspection")`` therefore resolves ambiguously, and
when mappers configure eagerly (the first ORM insert in a fresh ``AsyncSession``,
or any direct ``configure_mappers()`` call) SQLAlchemy raises::

    InvalidRequestError: Multiple classes found for path "Inspection" in the
    registry of this declarative base. Please use a fully module-qualified path.

The blast radius is wider than tests: that failure aborts the ``after_configured``
mapper event in ``app/db/session.py`` before ``register_cross_base_fk_resolution``
runs, silently disabling bare-name cross-base FK resolution whenever mappers are
configured eagerly.

The fix disambiguates every ``"Inspection"`` relationship target with its fully
module-qualified path (exactly what the error message recommends). This test pins
that fix so the ambiguity cannot regress.
"""

from __future__ import annotations

import os

# Hermetic: the mapper graph is identical regardless of runtime config, so pin
# safe defaults before importing the app to stay independent of ambient env / .env
# (these only fill gaps — ``setdefault`` never overrides a deliberately-set var).
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")


def test_configure_mappers_does_not_raise() -> None:
    """All mappers configure without the duplicate-``Inspection`` ambiguity.

    ``import app.db.base`` registers every model (including ``app.modules.*``) into
    the shared declarative registry; ``configure_mappers()`` then forces the full
    relationship-resolution pass that previously raised ``InvalidRequestError:
    Multiple classes found for path "Inspection"``.
    """
    from sqlalchemy.orm import configure_mappers

    import app.db.base  # noqa: F401  # side-effect: imports every model into the registry

    configure_mappers()


def test_after_configured_installs_cross_base_fk_mirrors() -> None:
    """The ``after_configured`` event must reach ``register_cross_base_fk_resolution``.

    This guards the *blast radius* of the duplicate-``Inspection`` bug: when
    ``configure_mappers()`` raised, the ``after_configured`` mapper event in
    ``app/db/session.py`` aborted before ``register_cross_base_fk_resolution`` ran,
    so the bare-name cross-base FK mirror tables (tagged ``info["cross_base_mirror"]``
    in ``TenantBase.metadata``) were *silently* never installed. Once configuration
    succeeds the event fires and the mirrors appear — proving the auto-registration
    path is live, not just that the raise is gone.
    """
    from sqlalchemy.orm import configure_mappers

    import app.db.base  # noqa: F401
    from app.db.session import TenantBase

    configure_mappers()

    mirrors = [t for t in TenantBase.metadata.tables.values() if t.info.get("cross_base_mirror")]
    assert mirrors, (
        "after_configured did not install cross-base FK mirror tables — "
        "register_cross_base_fk_resolution never ran via the mapper event"
    )


# Известные намеренные дубли имён mapped-классов (разные модули → разные таблицы,
# один declarative-реестр). Каждый — потенциальная ambiguity «Multiple classes
# found for path "X"», НО только если к нему обратиться строковым аргументом
# `relationship("X")` (forward-ref аннотации `Mapped["X"]` резолвятся в globals
# модуля класса и неоднозначности не дают). Сейчас таких строковых ссылок нет —
# дубли латентны. Этот пин фиксирует ровно текущий набор: появление НОВОГО дубля
# (или исчезновение старого) обязывает осознанно обновить список и проверить, что
# на имя нет ambiguous строкового ref.
KNOWN_DUPLICATE_MAPPED_NAMES = {
    "CorrectiveAction",  # app.models.checks + app.models.safety_ops
    "IncidentPerson",  # app.models.models + app.models.safety_ops
    "Inspection",  # app.models.models (regulatory_inspection) + app.models.checks
    "PlanTask",  # app.models.models + app.models.notifications
}


def test_duplicate_mapped_class_names_match_known_set() -> None:
    """Набор дублирующихся имён mapped-классов не должен меняться незаметно.

    Дубли сами по себе безопасны (разные таблицы, нет строковых ref), но каждый
    новый — это мина под `configure_mappers()`: первый же bare `relationship("X")`
    на дублированное имя поднимет `InvalidRequestError: Multiple classes found`.
    Падение этого теста = осознанно квалифицируй ссылки полным путём и обнови набор.
    """
    from collections import defaultdict

    import app.db.base  # noqa: F401  # импортирует все модели в реестр
    from app.db.session import SharedBase, TenantBase

    by_name: dict[str, list[str]] = defaultdict(list)
    for base in (SharedBase, TenantBase):
        for mapper in base.registry.mappers:
            cls = mapper.class_
            by_name[cls.__name__].append(f"{cls.__module__} -> {mapper.local_table.name}")

    duplicates = {name: sorted(v) for name, v in by_name.items() if len(v) > 1}
    unexpected = set(duplicates) - KNOWN_DUPLICATE_MAPPED_NAMES
    missing = KNOWN_DUPLICATE_MAPPED_NAMES - set(duplicates)
    assert not unexpected, (
        "Новые дублирующиеся имена mapped-классов (квалифицируй строковые "
        f"relationship-ссылки полным путём, затем добавь в набор): {dict((n, duplicates[n]) for n in unexpected)}"
    )
    assert (
        not missing
    ), f"Эти дубли исчезли — обнови KNOWN_DUPLICATE_MAPPED_NAMES: {sorted(missing)}"
    # Каждый дубль обязан указывать на РАЗНЫЕ таблицы (иначе это настоящая коллизия).
    for name, entries in duplicates.items():
        tables = {e.split(" -> ")[1] for e in entries}
        assert len(tables) == len(entries), f"{name}: дубли делят одну таблицу: {entries}"
