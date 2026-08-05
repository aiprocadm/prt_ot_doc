"""BIZ-49 срез-9: правила области видимости данных в контексте клиента."""

from __future__ import annotations

import pytest

from app.domains.managed_clients.context import ClientContext
from app.domains.managed_clients.lifecycle import ManagedClientMode
from app.domains.managed_clients.scope import (
    CLIENT_SCOPED_SECTIONS,
    ClientDataScope,
    resolve_client_scope,
    scoped_section_titles,
)


def _ctx(**kw) -> ClientContext:
    base = dict(
        user_id="u1",
        client_id="mc1",
        client_name="ООО Ромашка",
        all_modules=True,
        modules=(),
        mode=ManagedClientMode.LIGHTWEIGHT,
        company_id="co1",
    )
    base.update(kw)
    return ClientContext(**base)


def test_lightweight_client_scopes_data_to_its_company() -> None:
    scope = resolve_client_scope(_ctx())

    assert isinstance(scope, ClientDataScope)
    assert scope.company_id == "co1"
    assert scope.visible is True
    assert scope.reason is None


def test_dedicated_client_shows_nothing_instead_of_everything() -> None:
    """Данные такого клиента лежат в ДРУГОМ контуре — читать их нечем.

    Вернуть здесь данные аутсорсера значило бы показать чужие строки под
    вывеской «вы работаете от имени клиента» — худший из возможных ответов.
    """

    scope = resolve_client_scope(_ctx(mode=ManagedClientMode.DEDICATED, company_id=None))

    assert scope.visible is False
    assert scope.company_id is None
    assert "контур" in (scope.reason or "")


def test_client_without_company_shows_nothing_not_everything() -> None:
    """Клиент заведён, но с организацией ещё не связан.

    Fail-closed: «не знаю, чьи это данные» → показываем пусто. Обратное
    поведение (показать всё) — это утечка между клиентами одного аутсорсера.
    """

    scope = resolve_client_scope(_ctx(company_id=None))

    assert scope.visible is False
    assert scope.company_id is None
    assert scope.reason


def test_scope_keeps_client_identity_for_messages_and_audit() -> None:
    scope = resolve_client_scope(_ctx())

    assert scope.client_id == "mc1"
    assert scope.client_name == "ООО Ромашка"


@pytest.mark.parametrize("mode", list(ManagedClientMode))
def test_scope_never_falls_back_to_whole_tenant(mode: ManagedClientMode) -> None:
    """Ни один режим не даёт «фильтра нет — показываем всё»."""

    for company_id in (None, "co1"):
        scope = resolve_client_scope(_ctx(mode=mode, company_id=company_id))
        assert scope.visible == (scope.company_id is not None)


def test_sections_registry_is_declared_and_titled() -> None:
    """Реестр разделов — единственный источник правды для индикатора.

    Индикатор в интерфейсе обязан называть разделы, где фильтр РЕАЛЬНО
    действует. Захардкоженный на фронте список разъехался бы с бэкендом
    ровно в тот момент, когда добавят новый раздел.
    """

    assert CLIENT_SCOPED_SECTIONS
    titles = scoped_section_titles()
    assert len(titles) == len(CLIENT_SCOPED_SECTIONS)
    assert all(isinstance(t, str) and t.strip() for t in titles)
