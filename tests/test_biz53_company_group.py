"""BIZ-53 (Доп. №1 разд. 53.3): группа компаний внутри одного enterprise-tenant.

ТЗ: «Группа компаний / филиальная иерархия внутри одного enterprise-tenant».
Нижние уровни (Company → Branch → Site) существуют с RC-014; верхнего — связи
«головная → дочерние» — не было вовсе, хотя docstring модели ``Branch`` этот
уровень обещает («группы компаний → компании → филиалы …»).

Связь — ``Company.parent_company_id``, app-level reference БЕЗ DB FK (класс
миграционных граблей wa02, прецедент ``site.branch_id``). Раз базы-предохранителя
нет, каждый инвариант обязан держать API-слой — и каждый здесь доказан:

* родитель существует в ТОМ ЖЕ tenant (чужой/несуществующий → 422);
* компания не может быть головной сама себе (422);
* цикл запрещён: нельзя подчинить A той компании, что уже подчинена A (422);
* архив головной при живых дочках запрещён (409) — иначе дочки остаются
  с висячей ссылкой, которую некому поймать.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio

_API = "/api/v1/companies"


async def _create(client, headers, name: str, parent: str | None = None) -> dict:
    body: dict = {"name": name}
    if parent is not None:
        body["parent_company_id"] = parent
    response = await client.post(_API, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestГруппаКомпаний:
    async def test_дочка_создаётся_с_головной_и_связь_видна_в_ответе(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        holding = await _create(async_client, headers, "ГК Альфа (тест группы)")
        child = await _create(
            async_client, headers, "Альфа-Логистика (тест группы)", parent=holding["id"]
        )

        assert child["parent_company_id"] == holding["id"]

        got = await async_client.get(f"{_API}/{child['id']}", headers=headers)
        assert got.status_code == 200
        assert got.json()["parent_company_id"] == holding["id"]

    async def test_несуществующая_головная_отвергается_словами(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.post(
            _API,
            json={"name": "Сирота (тест группы)", "parent_company_id": "no-such-company"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "не найдена" in response.text

    async def test_сам_себе_головной_быть_нельзя(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        company = await _create(async_client, headers, "Нарцисс (тест группы)")
        response = await async_client.patch(
            f"{_API}/{company['id']}",
            json={"parent_company_id": company["id"]},
            headers=headers,
        )
        assert response.status_code == 422
        assert "самой себя" in response.text

    async def test_цикл_запрещён(self, async_client, make_auth_headers) -> None:
        """A ← B (B подчинена A). Попытка подчинить A компании B — круг."""

        headers = await make_auth_headers()
        a = await _create(async_client, headers, "Цикл-А (тест группы)")
        b = await _create(async_client, headers, "Цикл-Б (тест группы)", parent=a["id"])

        response = await async_client.patch(
            f"{_API}/{a['id']}",
            json={"parent_company_id": b["id"]},
            headers=headers,
        )
        assert response.status_code == 422
        assert "круг" in response.text

    async def test_архив_головной_при_живых_дочках_отказан(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        holding = await _create(async_client, headers, "ГК Бета (тест группы)")
        child = await _create(
            async_client, headers, "Бета-Строй (тест группы)", parent=holding["id"]
        )

        blocked = await async_client.delete(f"{_API}/{holding['id']}", headers=headers)
        assert blocked.status_code == 409
        assert "дочерние" in blocked.text

        # Переподчинения нет → архивируем дочку, потом головную: путь открыт.
        gone_child = await async_client.delete(f"{_API}/{child['id']}", headers=headers)
        assert gone_child.status_code == 204
        gone_holding = await async_client.delete(f"{_API}/{holding['id']}", headers=headers)
        assert gone_holding.status_code == 204

    async def test_снятие_привязки_нулём(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        holding = await _create(async_client, headers, "ГК Гамма (тест группы)")
        child = await _create(
            async_client, headers, "Гамма-Сервис (тест группы)", parent=holding["id"]
        )

        response = await async_client.patch(
            f"{_API}/{child['id']}",
            json={"parent_company_id": None},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["parent_company_id"] is None

    async def test_головная_из_чужого_tenant_не_видна(
        self, async_client, make_auth_headers, test_companies_multi_tenant
    ) -> None:
        """Tenant-scoped запрос не находит чужую компанию → та же 422 «не найдена»:

        существование чужой записи не подтверждается (принцип 404-не-403)."""

        headers_a = await make_auth_headers(tenant="acme", email="admin-acme@example.com")
        headers_b = await make_auth_headers(tenant="beta", email="admin-beta@example.com")

        alien = await _create(async_client, headers_b, "Чужая ГК (тест группы)")
        response = await async_client.post(
            _API,
            json={"name": "Дочка через границу (тест группы)", "parent_company_id": alien["id"]},
            headers=headers_a,
        )
        assert response.status_code == 422
        assert "не найдена" in response.text
