"""Дисциплина происшествия (in01; Доп. №1 разд. 54.2 + кросс-контур).

ЗАЧЕМ. Инцидент на ОПО был неотличим от микротравмы в офисе: у происшествия
есть вид, тяжесть и стадия расследования, но нет отнесения к дисциплине.
Разд. 54.2 требует связь промбеза с «расследованиями инцидентов на ОПО», а
отчёт в Ростехнадзор спрашивает число инцидентов — и подсказать его было
нельзя честно: все происшествия организации — чужие числа.

ПРИЁМ ТОТ ЖЕ, что у курса обучения (cd06) и стажировки (tr06): общая ядровая
сущность + колонка ``discipline`` из ОБЩЕГО словаря. Контур дисциплины
отбирает свои записи и копии не заводит.

ЧТО ПРОВЕРЯЕТСЯ: код принимается и возвращается словами; пусто — «не
размечено», а НЕ «охрана труда»; неизвестный код — ошибка запроса, а не
тихая запись; разметку можно поставить, сменить и снять; список фильтруется
по дисциплине; чужие и неразмеченные в фильтр не попадают; ``discipline=none``
отбирает ТОЛЬКО неразмеченные (срез-65: отчёты называют их число — реестр
обязан их показать), но записать «none» дисциплиной нельзя.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.models.models import IncidentSeverity, IncidentType, RoleEnum
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

_API = "/api/v1/incidents"


async def _fixtures(sessionmaker, data_factory: TestDataFactory) -> tuple[str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()
        return str(company.id), str(site.id)


def _payload(company_id: str, site_id: str, **extra: object) -> dict[str, object]:
    return {
        "title": "Разгерметизация трубопровода",
        "incident_type": IncidentType.NEAR_MISS.value,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "company_id": company_id,
        "site_id": site_id,
        "severity": IncidentSeverity.MEDIUM.value,
        **extra,
    }


class TestРазметка:
    async def test_дисциплина_принимается_и_возвращается_словами(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        created = await async_client.post(
            _API,
            json=_payload(company_id, site_id, discipline="industrial_safety"),
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["discipline"] == "industrial_safety"
        assert body["discipline_label"] == "Промышленная безопасность"

        fetched = await async_client.get(f"{_API}/{body['id']}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["discipline_label"] == "Промышленная безопасность"

    async def test_без_дисциплины_пусто_а_не_охрана_труда(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Приписать записи принадлежность, которой в данных нет, нельзя."""

        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        created = await async_client.post(_API, json=_payload(company_id, site_id), headers=headers)
        assert created.status_code == 201, created.text
        assert created.json()["discipline"] is None
        assert created.json()["discipline_label"] is None

    async def test_неизвестный_код_отвергается(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        response = await async_client.post(
            _API, json=_payload(company_id, site_id, discipline="охрана труда"), headers=headers
        )
        assert response.status_code == 400, response.text
        assert "industrial_safety" in response.json()["detail"]["message"]

    async def test_все_коды_общего_словаря_принимаются(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Словарь ОДИН на весь продукт: у происшествия те же дисциплины, что
        у курса, стажировки и Центра внимания."""

        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        for discipline in Discipline:
            response = await async_client.post(
                _API,
                json=_payload(company_id, site_id, discipline=discipline.value),
                headers=headers,
            )
            assert response.status_code == 201, response.text
            assert response.json()["discipline_label"] == DISCIPLINE_TITLES[discipline]

    async def test_разметку_можно_сменить_и_снять(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        created = (
            await async_client.post(_API, json=_payload(company_id, site_id), headers=headers)
        ).json()

        marked = await async_client.patch(
            f"{_API}/{created['id']}", json={"discipline": "ecology"}, headers=headers
        )
        assert marked.status_code == 200, marked.text
        assert marked.json()["discipline_label"] == "Экология"

        wrong = await async_client.patch(
            f"{_API}/{created['id']}", json={"discipline": "nope"}, headers=headers
        )
        assert wrong.status_code == 400, wrong.text

        cleared = await async_client.patch(
            f"{_API}/{created['id']}", json={"discipline": None}, headers=headers
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["discipline"] is None
        assert cleared.json()["discipline_label"] is None


class TestФильтр:
    async def test_список_отбирает_свою_дисциплину(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Контур показывает СВОЁ; неразмеченные и чужие не подмешиваются."""

        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        for discipline in ("industrial_safety", "industrial_safety", "ecology", None):
            response = await async_client.post(
                _API, json=_payload(company_id, site_id, discipline=discipline), headers=headers
            )
            assert response.status_code == 201, response.text

        everything = await async_client.get(_API, headers=headers)
        assert everything.json()["total"] == 4

        own = await async_client.get(
            _API, params={"discipline": "industrial_safety"}, headers=headers
        )
        assert own.status_code == 200, own.text
        assert own.json()["total"] == 2
        assert all(i["discipline"] == "industrial_safety" for i in own.json()["items"])

    async def test_none_отбирает_только_неразмеченные(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Срез-65: ссылка «без разметки» из отчётов ведёт к своим записям."""

        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        for discipline in ("ecology", None, None):
            response = await async_client.post(
                _API, json=_payload(company_id, site_id, discipline=discipline), headers=headers
            )
            assert response.status_code == 201, response.text

        unmarked = await async_client.get(_API, params={"discipline": "none"}, headers=headers)
        assert unmarked.status_code == 200, unmarked.text
        assert unmarked.json()["total"] == 2
        assert all(i["discipline"] is None for i in unmarked.json()["items"])

        # Фильтр и полный список — разные ответы, а не один кэш (ETag).
        everything = await async_client.get(_API, headers=headers)
        assert everything.json()["total"] == 3
        assert everything.headers["etag"] != unmarked.headers["etag"]

    async def test_none_нельзя_записать_дисциплиной(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """«none» — слово фильтра, не код словаря: снятие разметки — null."""

        company_id, site_id = await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        created = await async_client.post(
            _API, json=_payload(company_id, site_id, discipline="none"), headers=headers
        )
        assert created.status_code == 400, created.text

        plain = (
            await async_client.post(_API, json=_payload(company_id, site_id), headers=headers)
        ).json()
        patched = await async_client.patch(
            f"{_API}/{plain['id']}", json={"discipline": "none"}, headers=headers
        )
        assert patched.status_code == 400, patched.text

    async def test_фильтр_по_неизвестной_дисциплине_отвергается(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        await _fixtures(sessionmaker, data_factory)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        response = await async_client.get(_API, params={"discipline": "nope"}, headers=headers)
        assert response.status_code == 400, response.text
