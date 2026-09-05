"""Контур экологии срез-71 (Доп. №1 разд. 55.3 + 57.2): сроки отчётности и платежей.

Требование разд. 55.3: «2-ТП (воздух, отходы, водхоз), декларация о плате,
авансовые платежи»; разд. 57.2: общий календарь и Центр внимания видят ВСЕ
дисциплины. До среза срок сдачи 2-ТП было некуда внести: расчёт платы был
(срез-6), а даты «когда сдать и заплатить» не было ни в календаре, ни в
Центре внимания — эколог помнил их в голове.

Решения:

* **дату вносит эколог, платформа её не вычисляет** — граница среза-23:
  сроки задают нормативные акты и меняются, вшитая в код дата отстанет;
* **состояние выводится при чтении** из двух дат (срок и исполнение), а не
  хранится: перенос срока не должен требовать ручного «пересчёта»;
* **исполненный срок в календарь и Центр внимания не попадает** — сданный
  отчёт не событие и не просрочка, иначе лежал бы «просроченным» вечно;
* **повтор «то же название на ту же дату» — ошибка запроса**, а не вторая
  строка: одинаковые сроки в календаре читаются как две обязанности.

Правило библиотеки правил и событие просрочки для этого источника — следующий
шаг: сторож ``test_правила_сроков_различают_источник`` требует правило на
каждый источник событий, а счёт правил (12) закреплён в тестах каталога.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline, discipline_of
from app.models.ecology import EcologyReportingDeadline
from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum, Tenant
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

_API = "/api/v1/ecology"


async def _grant(sessionmaker, code: str = "ecology", on: bool = True) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=code)
            session.add(feature)
            await session.flush()
        grant = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        else:
            grant.on = on
        await session.commit()


def _payload(**extra: object) -> dict[str, object]:
    return {
        "kind": "report",
        "title": "2-ТП (отходы) за прошлый год",
        "period": str(date.today().year - 1),
        "due_on": (date.today() + timedelta(days=30)).isoformat(),
        **extra,
    }


class TestРучки:
    async def test_без_модуля_ручки_нет(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/reporting-deadlines", headers=headers)
        assert response.status_code == 404, response.text

    async def test_срок_создаётся_и_читается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        await _grant(sessionmaker)
        headers = await make_auth_headers()
        created = await async_client.post(
            f"{_API}/reporting-deadlines", json=_payload(), headers=headers
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["kind_label"] == "Отчётность"
        assert body["status"] == "planned"
        assert body["status_label"] == "Предстоит"
        assert body["done_on"] is None

        listed = await async_client.get(f"{_API}/reporting-deadlines", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["title"] == "2-ТП (отходы) за прошлый год"

    async def test_прошедший_срок_без_отметки_просрочен(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        await _grant(sessionmaker)
        headers = await make_auth_headers()
        created = await async_client.post(
            f"{_API}/reporting-deadlines",
            json=_payload(
                kind="payment",
                title="Авансовый платёж за НВОС",
                due_on=(date.today() - timedelta(days=3)).isoformat(),
            ),
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["kind_label"] == "Платёж"
        assert created.json()["status"] == "overdue"
        assert created.json()["status_label"] == "Просрочено"

        overdue_only = await async_client.get(
            f"{_API}/reporting-deadlines", params={"status": "overdue"}, headers=headers
        )
        assert overdue_only.json()["total"] == 1

    async def test_отметка_исполнения_переводит_в_исполнено_и_снимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Состояние — из двух дат при чтении; ``done_on: null`` возвращает срок в работу."""

        await _grant(sessionmaker)
        headers = await make_auth_headers()
        created = (
            await async_client.post(
                f"{_API}/reporting-deadlines",
                json=_payload(due_on=(date.today() - timedelta(days=3)).isoformat()),
                headers=headers,
            )
        ).json()

        done = await async_client.patch(
            f"{_API}/reporting-deadlines/{created['id']}",
            json={"done_on": (date.today() - timedelta(days=4)).isoformat()},
            headers=headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "done"
        assert done.json()["status_label"] == "Исполнено"

        reopened = await async_client.patch(
            f"{_API}/reporting-deadlines/{created['id']}",
            json={"done_on": None},
            headers=headers,
        )
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["status"] == "overdue"

    async def test_неизвестный_вид_и_состояние_отвергаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        await _grant(sessionmaker)
        headers = await make_auth_headers()
        wrong_kind = await async_client.post(
            f"{_API}/reporting-deadlines", json=_payload(kind="декларация"), headers=headers
        )
        assert wrong_kind.status_code == 422, wrong_kind.text
        assert "report" in wrong_kind.text and "payment" in wrong_kind.text

        wrong_status = await async_client.get(
            f"{_API}/reporting-deadlines", params={"status": "late"}, headers=headers
        )
        assert wrong_status.status_code == 422, wrong_status.text

    async def test_повтор_названия_на_ту_же_дату_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        await _grant(sessionmaker)
        headers = await make_auth_headers()
        first = await async_client.post(
            f"{_API}/reporting-deadlines", json=_payload(), headers=headers
        )
        assert first.status_code == 201, first.text
        second = await async_client.post(
            f"{_API}/reporting-deadlines", json=_payload(), headers=headers
        )
        assert second.status_code == 422, second.text
        assert "уже внесён" in second.json()["detail"]["message"]

        # Та же строка на другую дату — не повтор: сроки переносят.
        other_day = await async_client.post(
            f"{_API}/reporting-deadlines",
            json=_payload(due_on=(date.today() + timedelta(days=60)).isoformat()),
            headers=headers,
        )
        assert other_day.status_code == 201, other_day.text

    async def test_сводка_считает_просроченную_отчётность(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Исполненное с прошедшим сроком — не просрочка."""

        await _grant(sessionmaker)
        headers = await make_auth_headers()
        past = (date.today() - timedelta(days=3)).isoformat()
        for title, done_on in (("2-ТП (воздух)", None), ("2-ТП (водхоз)", past)):
            created = await async_client.post(
                f"{_API}/reporting-deadlines",
                json=_payload(title=title, due_on=past, done_on=done_on),
                headers=headers,
            )
            assert created.status_code == 201, created.text

        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["reporting_overdue"] == 1


class TestКалендарьИЦентрВнимания:
    async def test_источник_объявлен_и_размечен_экологией(self) -> None:
        """Без разметки срок ушёл бы в «не классифицировано», а не в строку «Экология»."""

        assert "ecology_report" in ALL_SOURCES
        assert discipline_of("ecology_report") is Discipline.ECOLOGY

    async def test_календарь_показывает_невыполненные_и_прячет_исполненные(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        test_db_session.add_all(
            [
                EcologyReportingDeadline(
                    tenant_id=tid,
                    kind="report",
                    title="2-ТП (отходы)",
                    due_on=date.today() - timedelta(days=2),
                ),
                EcologyReportingDeadline(
                    tenant_id=tid,
                    kind="payment",
                    title="Авансовый платёж, I квартал",
                    period="1 кв.",
                    due_on=date.today() + timedelta(days=20),
                ),
                # Исполненный с прошедшим сроком — НЕ событие: иначе он лежал
                # бы «просроченным» вечно.
                EcologyReportingDeadline(
                    tenant_id=tid,
                    kind="report",
                    title="Декларация о плате",
                    due_on=date.today() - timedelta(days=10),
                    done_on=date.today() - timedelta(days=12),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(source_types=["ecology_report"], include_sla=True)

        assert response.total == 2
        assert response.overdue_count == 1
        titles = [item.title for item in response.items]
        assert titles == ["Отчётность: 2-ТП (отходы)", "Платёж: Авансовый платёж, I квартал"]
        overdue = response.items[0]
        assert overdue.is_overdue is True
        assert overdue.status == "overdue"
        assert overdue.sla_band == "overdue"
        assert overdue.extra["kind"] == "report"
        assert response.items[1].extra["period"] == "1 кв."
        counts = {row.source_type: row for row in response.by_source}
        assert counts["ecology_report"].count == 2
        assert counts["ecology_report"].overdue_count == 1

    async def test_чужой_арендатор_сроков_не_видит(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        test_db_session.add(
            EcologyReportingDeadline(
                tenant_id="someone-else",
                kind="report",
                title="Чужая 2-ТП",
                due_on=date.today() - timedelta(days=2),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(source_types=["ecology_report"])
        assert response.total == 0

    async def test_просроченный_срок_доходит_до_центра_внимания(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Разд. 57.2: строка «Экология» и пункт ленты — без вручного обхода."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await data_factory.set_modules(session, tenant.id, ("ecology",))
            session.add(
                EcologyReportingDeadline(
                    tenant_id=str(tenant.id),
                    kind="report",
                    title="2-ТП (воздух)",
                    due_on=date.today() - timedelta(days=5),
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get("/api/v1/workspace/attention", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        items = [item for item in body["items"] if item["item_type"] == "ecology_report"]
        assert len(items) == 1, body["items"]
        assert items[0]["discipline"] == "ecology"
        assert items[0]["title"] == "Отчётность: 2-ТП (воздух)"
        assert items[0]["severity"] in {"critical", "high"}
        ecology = next(row for row in body["disciplines"] if row["code"] == "ecology")
        assert ecology["overdue"] >= 1
