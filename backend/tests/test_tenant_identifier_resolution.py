"""Общий резолвер арендатора обязан быть однозначным, а не падать 500.

`_fetch_tenant_by_identifier` ищет по slug, коду И (для 36-символьной строки)
по id одним `OR`-запросом. Совпасть может СРАЗУ НЕСКОЛЬКО арендаторов: код
одного бывает равен slug'у другого, а в тестовых данных встречается арендатор,
чей slug равен UUID соседа. Прежний `scalar_one_or_none()` в этом случае бросал
`MultipleResultsFound`, и пользователь получал «внутреннюю ошибку» на обычном
запросе — вместо работы.

Дефект был латентным: его вскрыл полный прогон после того, как биллинг-гейт
перевели на этот же резолвер. Здесь закрепляется явный порядок предпочтения
id → slug → код.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import dependencies
from app.models.models import Tenant

UUID_OF_FIRST = "11111111-2222-3333-4444-555555555555"


def _tenant(**kwargs) -> Tenant:
    defaults = {
        "id": UUID_OF_FIRST,
        "slug": "acme",
        "name": "ACME",
        "code": "acme-1",
        "schema_name": "tenant_acme",
        "is_active": True,
    }
    defaults.update(kwargs)
    return Tenant(**defaults)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return iter(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return _Result(self._rows)


@pytest.fixture()
def rows(monkeypatch: pytest.MonkeyPatch):
    holder: list[list[Tenant]] = [[]]

    monkeypatch.setattr(dependencies, "AsyncSessionLocal", lambda **_: _Session(holder[0]))
    monkeypatch.setattr(dependencies, "ensure_tenant_schema", lambda *a, **k: None)
    return holder


@pytest.mark.asyncio
async def test_uuid_wins_over_a_namesake_slug(rows) -> None:
    """Ровно тот случай, что ронял запрос 500-й."""

    target = _tenant()
    impostor = _tenant(id="99999999-0000-0000-0000-000000000000", slug=UUID_OF_FIRST, code="x")
    rows[0] = [impostor, target]  # порядок из БД произвольный

    resolved = await dependencies._fetch_tenant_by_identifier(UUID_OF_FIRST)

    assert resolved.id == UUID_OF_FIRST


@pytest.mark.asyncio
async def test_slug_wins_over_someone_elses_code(rows) -> None:
    by_slug = _tenant(slug="beta", code="beta-code")
    by_code = _tenant(id="88888888-0000-0000-0000-000000000000", slug="gamma", code="beta")
    rows[0] = [by_code, by_slug]

    resolved = await dependencies._fetch_tenant_by_identifier("beta")

    assert resolved.slug == "beta"


@pytest.mark.asyncio
async def test_code_still_resolves_when_nothing_else_matches(rows) -> None:
    rows[0] = [_tenant()]

    resolved = await dependencies._fetch_tenant_by_identifier("acme-1")

    assert resolved.code == "acme-1"


@pytest.mark.asyncio
async def test_missing_tenant_is_404(rows) -> None:
    rows[0] = []

    with pytest.raises(HTTPException) as excinfo:
        await dependencies._fetch_tenant_by_identifier("nobody")

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_inactive_tenant_is_403(rows) -> None:
    rows[0] = [_tenant(is_active=False)]

    with pytest.raises(HTTPException) as excinfo:
        await dependencies._fetch_tenant_by_identifier("acme")

    assert excinfo.value.status_code == 403
