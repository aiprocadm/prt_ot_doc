"""Unit: BIZ-49 срез-6 — правила матрицы доступа «специалист → клиент» (разд. 49.3).

ТЗ: «какие специалисты аутсорсера к каким клиентам и модулям допущены».
Это контроль доступа, поэтому здесь важнее всего умолчания: неясность в них
и есть та дыра, через которую доступ утекает.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domains.managed_clients.access import (
    AccessGrant,
    AccessGrantError,
    grant_allows,
    is_grant_active,
    validate_grant,
    visible_client_ids,
)

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _grant(
    *,
    client_id="mc1",
    user_id="u1",
    all_modules=False,
    modules=None,
    revoked_at=None,
) -> AccessGrant:
    return AccessGrant(
        client_id=client_id,
        user_id=user_id,
        all_modules=all_modules,
        modules=tuple(modules or ()),
        revoked_at=revoked_at,
    )


class TestValidate:
    def test_module_list_grant_is_valid(self):
        validate_grant(all_modules=False, modules=("documents", "training"))

    def test_all_modules_grant_is_valid(self):
        validate_grant(all_modules=True, modules=())

    def test_empty_grant_is_rejected(self):
        """Грант «ни одного модуля и не весь клиент» ничего не даёт — это
        всегда опечатка, и молча создавать пустышку нельзя."""
        with pytest.raises(AccessGrantError):
            validate_grant(all_modules=False, modules=())

    def test_contradictory_grant_is_rejected(self):
        """«Весь клиент» ВМЕСТЕ со списком модулей — два разных намерения
        в одной строке; какое из них правда, потом не докажешь."""
        with pytest.raises(AccessGrantError):
            validate_grant(all_modules=True, modules=("documents",))

    def test_duplicate_modules_are_rejected(self):
        with pytest.raises(AccessGrantError):
            validate_grant(all_modules=False, modules=("documents", "documents"))


class TestGrantAllows:
    def test_module_grant_allows_listed_module(self):
        assert grant_allows(_grant(modules=("documents",)), module="documents", now=_NOW)

    def test_module_grant_denies_unlisted_module(self):
        """Умолчание — ЗАПРЕТ: не перечислен, значит нет доступа."""
        assert not grant_allows(_grant(modules=("documents",)), module="training", now=_NOW)

    def test_all_modules_grant_allows_anything(self):
        assert grant_allows(_grant(all_modules=True), module="training", now=_NOW)

    def test_revoked_grant_allows_nothing(self):
        revoked = _grant(all_modules=True, revoked_at=_NOW)
        assert not grant_allows(revoked, module="training", now=_NOW)

    def test_revocation_is_effective_from_its_moment(self):
        """Отозванный вчера грант не действует сегодня — и наоборот, проверка
        «на момент» позволяет разбирать прошлые действия в аудите."""
        from datetime import timedelta

        revoked_tomorrow = _grant(all_modules=True, revoked_at=_NOW + timedelta(days=1))
        assert grant_allows(revoked_tomorrow, module="x", now=_NOW)
        assert not grant_allows(revoked_tomorrow, module="x", now=_NOW + timedelta(days=2))

    def test_module_check_without_module_asks_about_client_itself(self):
        """`module=None` — вопрос «пустят ли к клиенту вообще»."""
        assert grant_allows(_grant(modules=("documents",)), module=None, now=_NOW)
        assert not grant_allows(
            _grant(modules=("documents",), revoked_at=_NOW), module=None, now=_NOW
        )


class TestIsActive:
    def test_active_and_revoked(self):
        assert is_grant_active(_grant(all_modules=True), now=_NOW)
        assert not is_grant_active(_grant(all_modules=True, revoked_at=_NOW), now=_NOW)


class TestVisibleClients:
    def test_only_own_active_grants(self):
        grants = [
            _grant(client_id="mc1", user_id="u1", all_modules=True),
            _grant(client_id="mc2", user_id="u1", all_modules=True, revoked_at=_NOW),
            _grant(client_id="mc3", user_id="u2", all_modules=True),
        ]
        assert visible_client_ids(grants, user_id="u1", now=_NOW) == {"mc1"}

    def test_no_grants_means_no_clients(self):
        """Отсутствие гранта — это НЕ «доступ ко всему портфелю»."""
        assert visible_client_ids([], user_id="u1", now=_NOW) == set()

    def test_module_scoped_grant_still_shows_the_client(self):
        grants = [_grant(client_id="mc1", user_id="u1", modules=("documents",))]
        assert visible_client_ids(grants, user_id="u1", now=_NOW) == {"mc1"}


def test_naive_revocation_date_does_not_crash():
    """Из БД дата может прийти без часового пояса (SQLite и часть драйверов):
    проверка доступа не имеет права падать из-за формата хранения времени."""
    from datetime import datetime as _dt

    naive = _dt(2026, 8, 4, 12, 0)  # без tzinfo
    grant = _grant(all_modules=True, revoked_at=naive)
    assert is_grant_active(grant, now=_NOW) is False
    assert grant_allows(grant, module=None, now=_NOW) is False
