"""BIZ-54-57 срез-3: карточка площадки 360° по HTTP (Доп. №1 разд. 57.1).

Правила проверены построчно в ``tests/test_site_overview_360.py``; здесь —
связка целиком через живой HTTP. Закрепляется то, что видно только на настоящей
базе:

* сотрудник попадает в светофор площадки ТОЛЬКО через рабочее место;
* человек без рабочего места в счёт площадки не входит, но назван числом —
  иначе зелёная карточка означала бы «всё хорошо» там, где людей не разнесли;
* наряды-допуски считаются только действующие и раскладываются по дисциплинам;
* чужая площадка — 404, а не чужие данные.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.feature import Feature, FeatureEnablement
from app.models.fire_safety import (
    FireDrill,
    FireMaintenanceRecord,
    FireSafetyDocument,
    FireSafetyEquipment,
)
from app.models.master_data import Company, Site, Workplace
from app.models.medical import MedicalExamKind, MedicalNorm
from app.models.models import Position, RoleEnum, Tenant
from app.models.work_permit import WorkPermit

BASE = "/api/v1/sites"

#: Пять дисциплин Доп. №1 — продаваемые модули; по умолчанию у арендатора
#: теста они НЕ выданы (BIZ-61), и карточка их не показывает (срез-54).
DISCIPLINE_MODULES = (
    "fire_safety",
    "industrial_safety",
    "ecology",
    "civil_defense",
    "road_safety",
)


@pytest.fixture()
async def site_with_people(sessionmaker, data_factory):
    """Площадка с рабочим местом, сотрудником на нём и сотрудником без места."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # Редакция «всё включено»: иначе на карточке остались бы три дисциплины ядра.
        await data_factory.set_modules(session, tenant.id, DISCIPLINE_MODULES, on=True)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Слесарь")
        session.add(position)
        await session.flush()
        session.add(
            MedicalNorm(
                tenant_id=tenant.id,
                position_id=position.id,
                exam_kind=MedicalExamKind.PERIODIC,
                interval_days=365,
            )
        )
        site = Site(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Цех №1",
            address="ул. Заводская, 1",
            is_hazardous_production_facility=True,
            opo_register_number="А12-3456",
        )
        session.add(site)
        await session.flush()
        workplace = Workplace(
            tenant_id=tenant.id,
            company_id=company.id,
            site_id=site.id,
            name="Пост сварки",
        )
        session.add(workplace)
        await session.flush()
        # На площадке — попадает в светофор.
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Иванов",
            position_id=position.id,
            workplace_id=workplace.id,
            session=session,
        )
        # Без рабочего места — к площадке не отнесён, но обязан быть назван.
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Петров",
            position_id=position.id,
            session=session,
        )
        await session.commit()
        return tenant, site.id


async def _foreign_site() -> str:
    """Площадка СОСЕДНЕГО арендатора — существующая, но чужая."""

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        tenant_id = (
            await session.execute(select(Tenant.id).where(Tenant.slug == "acme"))
        ).scalar_one()
        company = Company(tenant_id=tenant_id, name="ООО Сосед")
        session.add(company)
        await session.flush()
        site = Site(tenant_id=tenant_id, company_id=company.id, name="Чужой цех")
        session.add(site)
        await session.commit()
        return str(site.id)


async def _overview(async_client: AsyncClient, headers, site_id: str) -> dict:
    response = await async_client.get(f"{BASE}/{site_id}/overview", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _row(body: dict, discipline: str) -> dict:
    return next(r for r in body["disciplines"] if r["discipline"] == discipline)


@pytest.mark.anyio
class TestSiteOverview:
    async def test_человек_попадает_в_светофор_через_рабочее_место(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        _tenant, site_id = site_with_people
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        assert body["facts"]["people"] == 1, "второй человек — без рабочего места"
        assert body["facts"]["workplaces"] == 1
        medical = _row(body, "medical")
        # Норма есть, экзамена нет вовсе → красный с расшифровкой.
        assert medical["light"] == "red"
        assert medical["required"] == 1 and medical["missing"] == 1
        assert body["overall"] == "red"

    async def test_человек_без_рабочего_места_назван_числом(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        """Молчание про него однажды прочитают как «у площадки все учтены»."""

        _tenant, site_id = site_with_people
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        assert body["facts"]["people_without_workplace"] == 1

    async def test_все_дисциплины_тз_на_одном_экране(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        """Приёмка §58.3: статус по ВСЕМ ПРИМЕНИМЫМ дисциплинам (все модули выданы)."""

        _tenant, site_id = site_with_people
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        assert {r["discipline"] for r in body["disciplines"]} == {
            "medical",
            "ppe",
            "training",
            "fire_safety",
            "industrial_safety",
            "ecology",
            "civil_defense",
            "road_safety",
        }
        for row in body["disciplines"]:
            assert row["reason"].strip(), row["discipline"]

    async def test_опо_виден_в_расшифровке_промбеза(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        _tenant, site_id = site_with_people
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        assert body["is_hazardous_production_facility"] is True
        assert "А12-3456" in _row(body, "industrial_safety")["reason"]

    async def test_наряды_считаются_только_действующие_и_по_дисциплинам(
        self, async_client: AsyncClient, make_auth_headers, site_with_people, sessionmaker
    ) -> None:
        tenant, site_id = site_with_people
        async with sessionmaker() as session:
            for work_type, status_value in (
                ("hot_work", "issued"),
                ("hot_work", "closed"),  # уже не работа — в счёт не идёт
                ("gas_hazardous", "suspended"),
                ("height", "issued"),  # общая охрана труда — без дисциплины
                ("electrical", "draft"),  # ещё не работа
            ):
                session.add(
                    WorkPermit(
                        tenant_id=tenant.id,
                        work_type=work_type,
                        zone_text="участок",
                        site_id=site_id,
                        status=status_value,
                    )
                )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        permits = body["facts"]["permits"]
        assert permits["total"] == 3, permits
        assert permits["by_discipline"] == {"fire_safety": 1, "industrial_safety": 1}
        assert permits["without_discipline"] == 1
        assert permits["without_discipline_titles"] == ["работа на высоте"]
        # Причина обязана доехать до экрана: иначе «без дисциплины: 1»
        # прочитают как недоделку разметки, а не как решение.
        assert "охрана труда" in permits["without_discipline_reason"]

    async def test_наряды_не_красят_дисциплину(
        self, async_client: AsyncClient, make_auth_headers, site_with_people, sessionmaker
    ) -> None:
        """Документ о работах не доказывает соответствия — цвет не меняется."""

        tenant, site_id = site_with_people
        async with sessionmaker() as session:
            session.add(
                WorkPermit(
                    tenant_id=tenant.id,
                    work_type="hot_work",
                    zone_text="участок",
                    site_id=site_id,
                    status="issued",
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        fire = _row(body, "fire_safety")
        assert fire["light"] == "not_measured"
        assert "нарядов-допусков: 1" in fire["reason"]

    async def test_сроки_пб_площадки_красят_её_строку_а_чужие_и_без_площадки_нет(
        self, async_client: AsyncClient, make_auth_headers, site_with_people, sessionmaker
    ) -> None:
        """Срез-82 (разд. 54.1): просрочка объекта — красный, с фактами; сводка
        модуля считает то же самое по всему арендатору."""

        from datetime import date, timedelta

        tenant, site_id = site_with_people
        today = date.today()
        async with sessionmaker() as session:
            company_id = (
                await session.execute(select(Site.company_id).where(Site.id == site_id))
            ).scalar_one()
            other = Site(tenant_id=tenant.id, company_id=company_id, name="Цех №2")
            session.add(other)
            await session.flush()
            ok_unit = FireSafetyEquipment(
                tenant_id=tenant.id,
                site_id=site_id,
                kind="extinguisher",
                label="ОП-4 №1",
                recharge_due=today + timedelta(days=200),
            )
            session.add_all(
                [
                    # своя площадка: просроченная перезарядка — красный
                    FireSafetyEquipment(
                        tenant_id=tenant.id,
                        site_id=site_id,
                        kind="extinguisher",
                        label="ОП-4 №2",
                        recharge_due=today - timedelta(days=3),
                    ),
                    ok_unit,
                    # чужая площадка и без площадки — не сюда
                    FireSafetyEquipment(
                        tenant_id=tenant.id,
                        site_id=other.id,
                        kind="extinguisher",
                        label="ОП-4 №3",
                        recharge_due=today - timedelta(days=30),
                    ),
                    FireSafetyEquipment(
                        tenant_id=tenant.id,
                        kind="extinguisher",
                        label="ОП-4 №4",
                        inspection_due=today - timedelta(days=30),
                    ),
                    FireDrill(
                        tenant_id=tenant.id,
                        site_id=site_id,
                        kind="evacuation",
                        title="Эвакуация",
                        planned_on=today - timedelta(days=40),
                        held_on=today - timedelta(days=40),
                        outcome="satisfactory",
                    ),
                    FireSafetyDocument(
                        tenant_id=tenant.id,
                        site_id=site_id,
                        kind="evacuation_plan",
                        title="План эвакуации",
                        review_due=today - timedelta(days=1),
                    ),
                ]
            )
            await session.flush()
            session.add(
                FireMaintenanceRecord(
                    tenant_id=tenant.id,
                    equipment_id=ok_unit.id,
                    kind="recharge",
                    performed_on=today - timedelta(days=10),
                    result="passed",
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        fire = _row(body, "fire_safety")
        assert fire["light"] == "red", fire
        assert fire["reason"].startswith(
            "Просрочено по ПБ — перезарядка средств защиты: 1, пересмотр документов: 1; "
            "средств без записи о работах: 1; последняя тренировка "
        ), fire["reason"]
        assert "(40 дн. назад)" in fire["reason"]
        assert fire["required"] == 2 and fire["lapsed"] == 2
        assert body["overall"] == "red"

        # соседняя площадка видит только своё, средство без площадки — ничьё
        neighbour = _row(await _overview(async_client, headers, str(other.id)), "fire_safety")
        assert neighbour["light"] == "red"
        assert neighbour["reason"].startswith(
            "Просрочено по ПБ — перезарядка средств защиты: 1; "
            "средств без записи о работах: 1; проведённых тренировок нет"
        ), neighbour["reason"]

        # сводка модуля — та же формула по всему арендатору
        readiness = await async_client.get("/api/v1/fire-safety/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        summary = readiness.json()
        assert summary["total_units"] == 4
        assert summary["overdue_recharge"] == 2
        assert summary["overdue_inspection"] == 1
        assert summary["units_without_maintenance"] == 3
        assert summary["overdue_documents"] == 1
        assert summary["days_since_last_drill"] == 40

    async def test_непосчитанное_названо_с_причиной(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        _tenant, site_id = site_with_people
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        assert {row["title"] for row in body["not_counted"]} == {
            "Проверки",
            "Инциденты",
            "Риски",
        }

    async def test_дисциплины_вне_редакции_скрыты_и_названы(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        site_with_people,
        sessionmaker,
        data_factory,
    ) -> None:
        """Приёмка §58.3: дисциплины включаются флагами; скрытое не молчит (срез-54)."""

        tenant, site_id = site_with_people
        async with sessionmaker() as session:
            # «Экология» выключена после выдачи, «ГО и ЧС» — никогда не выдавалась
            # (строка выдачи удалена): на карточке оба случая равны.
            await data_factory.set_modules(session, tenant.id, ("ecology",), on=False)
            civil_defense = (
                await session.execute(select(Feature.id).where(Feature.code == "civil_defense"))
            ).scalar_one()
            await session.execute(
                delete(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == civil_defense,
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _overview(async_client, headers, site_id)

        assert [r["discipline"] for r in body["disciplines"]] == [
            "medical",
            "ppe",
            "training",
            "fire_safety",
            "industrial_safety",
            "road_safety",
        ]
        assert body["overall"] == "red", "итог считался по оставшимся — красный медосмотр на месте"
        hidden = next(r for r in body["not_counted"] if r["title"] == "Дисциплины вне редакции")
        assert hidden["reason"].startswith("Экология, ГО и ЧС — модуль не выдан")

    async def test_несуществующая_площадка_отвечает_404(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        _tenant, _site_id = site_with_people
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get(
            f"{BASE}/00000000-0000-0000-0000-000000000000/overview", headers=headers
        )

        assert response.status_code == 404, response.text

    async def test_админ_чужой_компании_карточку_не_получает(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        site_with_people,
        sessionmaker,
        data_factory,
    ) -> None:
        """Урок среза-1: у аутсорсера в одном арендаторе много компаний.

        Читатель, привязанный к компании, не должен видеть сводку по людям
        ЧУЖОЙ компании — это персональные данные, а не косметика. Ответ 404:
        403 подтвердил бы, что такая площадка есть.
        """

        tenant, site_id = site_with_people
        async with sessionmaker() as session:
            other_company = await data_factory.create_company(
                tenant=tenant, name="ООО Другая", session=session
            )
            # Привязка читателя к компании живёт в его учётной записи — именно
            # из неё берётся claim company_id.
            await data_factory.create_user(
                tenant=tenant,
                email="admin-other-company@example.com",
                role=RoleEnum.ADMIN,
                company_id=other_company.id,
                session=session,
            )
        headers = await make_auth_headers(RoleEnum.ADMIN, email="admin-other-company@example.com")

        response = await async_client.get(f"{BASE}/{site_id}/overview", headers=headers)

        assert response.status_code == 404, response.text

    async def test_админ_своей_компании_карточку_получает(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        site_with_people,
        sessionmaker,
        data_factory,
    ) -> None:
        """Обратная половина: сужение не должно закрывать СВОЮ площадку."""

        tenant, site_id = site_with_people
        async with sessionmaker() as session:
            company_id = (
                await session.execute(select(Site.company_id).where(Site.id == site_id))
            ).scalar_one()
            await data_factory.create_user(
                tenant=tenant,
                email="admin-own-company@example.com",
                role=RoleEnum.ADMIN,
                company_id=str(company_id),
                session=session,
            )
        headers = await make_auth_headers(RoleEnum.ADMIN, email="admin-own-company@example.com")

        response = await async_client.get(f"{BASE}/{site_id}/overview", headers=headers)

        assert response.status_code == 200, response.text

    async def test_площадка_чужого_арендатора_не_отдаётся(
        self, async_client: AsyncClient, make_auth_headers, site_with_people
    ) -> None:
        """Настоящая проверка изоляции: площадка СУЩЕСТВУЕТ, но у соседа.

        Несуществующий id доказывает только «404 бывает»: такой ответ вернёт и
        ручка, забывшая условие по арендатору.
        """

        _tenant, _site_id = site_with_people
        foreign = await _foreign_site()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get(f"{BASE}/{foreign}/overview", headers=headers)

        assert response.status_code == 404, response.text
