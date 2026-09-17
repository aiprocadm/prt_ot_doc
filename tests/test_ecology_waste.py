"""Контур экологии срез-2 (Доп. №1 разд. 55.2): отходы.

Требование: «паспорта отходов I–IV класса, учёт образования/движения/передачи,
лимиты, договоры с операторами, журналы учёта отходов».

СВЕРКА. После среза-1 у экологии есть только реестр объектов НВОС. Отходов нет
ни в каком виде: единственное упоминание — комплект документов ``ECO_WASTE``,
который печатает реестр, договор и памятку из введённых руками строк и ничего
не сохраняет.

Решения, которые важнее кода:

* **паспорт — I–IV класса, и это не описка ТЗ.** Пятый класс (практически
  неопасные отходы) паспортизации не подлежит, поэтому словарь закрыт четырьмя
  значениями;
* **журнал учёта отходов — это и есть список движений**, а не ядровой
  ``Journal``: у ядровой записи журнала ``person_id`` NOT NULL, а движение
  отходов к человеку не привязано вовсе. Ложить его туда значило бы ломать
  схему ради названия;
* **договоры с операторами НЕ дублируются**: в ядре есть ``Contract``
  (контрагент, номер, срок, сумма), и движение ссылается на него, а не заводит
  свой договор.

ГРАНИЦА: лимит платформа НЕ РАССЧИТЫВАЕТ — он берётся из нормативов образования
отходов и лимитов на их размещение (НООЛР) или декларации. Превышение
считается только тогда, когда лимит внесён; без лимита никакого суждения нет.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.ecology import WASTE_HAZARD_CLASSES, WASTE_MOVEMENT_KINDS
from app.models.feature import Feature, FeatureEnablement
from app.models.finance import Contract, ContractStatus
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/ecology"
_FRONTEND_ECOLOGY_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "ecology.ts"
)


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


async def _passport(async_client, headers, **overrides) -> str:
    payload = {
        "name": "Отходы минеральных масел моторных",
        "fkko_code": "40611001313",
        "hazard_class": "III",
    }
    payload.update(overrides)
    response = await async_client.post(f"{_API}/waste-passports", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestПаспортаОтходов:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/waste-passports", headers=headers)
        assert response.status_code == 404

    async def test_паспорт_заводится_с_классом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/waste-passports",
            json={
                "name": "Отходы минеральных масел моторных",
                "fkko_code": "40611001313",
                "hazard_class": "III",
                "approved_on": str(date.today() - timedelta(days=100)),
                "annual_limit_tons": "12.500",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["hazard_class_label"].startswith("III класс")
        assert body["annual_limit_tons"] == "12.500"

    async def test_пятый_класс_не_паспортизуется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ТЗ говорит «паспорта отходов I–IV класса» — и это не описка.

        Отходы V класса (практически неопасные) паспортизации не подлежат,
        поэтому словарь закрыт четырьмя значениями.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/waste-passports",
            json={"name": "Бой кирпича", "fkko_code": "34321001205", "hazard_class": "V"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный класс опасности" in response.text

    async def test_код_фкко_обязателен_и_не_дублируется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Код ФККО — удостоверение вида отхода: два паспорта на один код это
        один вид, заведённый дважды, и учёт по нему стал бы враньём."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _passport(async_client, headers, fkko_code="40611001313")
        second = await async_client.post(
            f"{_API}/waste-passports",
            json={
                "name": "То же масло",
                "fkko_code": "40611001313",
                "hazard_class": "III",
            },
            headers=headers,
        )
        assert second.status_code == 422
        assert "уже заведён" in second.text

        without_code = await async_client.post(
            f"{_API}/waste-passports",
            json={"name": "Без кода", "hazard_class": "IV"},
            headers=headers,
        )
        assert without_code.status_code == 422


class TestУчётДвижения:
    async def test_образование_и_передача_учитываются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(async_client, headers)
        today = date.today()

        generated = await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "generated",
                "happened_on": str(today - timedelta(days=10)),
                "quantity_tons": "3.250",
            },
            headers=headers,
        )
        assert generated.status_code == 201, generated.text
        assert generated.json()["kind_label"] == "Образование"

        transferred = await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "transferred",
                "happened_on": str(today),
                "quantity_tons": "3.000",
                "counterparty": "ООО «Экооператор»",
            },
            headers=headers,
        )
        assert transferred.status_code == 201, transferred.text
        assert transferred.json()["kind_label"] == "Передача оператору"

    async def test_журнал_учёта_это_список_движений(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ядровой Journal не годится: его запись обязана иметь person_id.

        Движение отходов к человеку не привязано вовсе, поэтому журнал учёта —
        это список движений по паспорту, отсортированный по дате.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(async_client, headers, fkko_code="91120001393")
        today = date.today()
        for shift in (60, 5):
            response = await async_client.post(
                f"{_API}/waste-movements",
                json={
                    "passport_id": passport_id,
                    "kind": "generated",
                    "happened_on": str(today - timedelta(days=shift)),
                    "quantity_tons": "1.000",
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = await async_client.get(
            f"{_API}/waste-movements", params={"passport_id": passport_id}, headers=headers
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 2
        # свежая запись — первой
        assert listed.json()["items"][0]["happened_on"] == str(today - timedelta(days=5))

    async def test_неизвестный_вид_движения_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(async_client, headers, fkko_code="73310001724")
        response = await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "выкинули",
                "happened_on": str(date.today()),
                "quantity_tons": "1.000",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный вид движения" in response.text

    async def test_нулевая_масса_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Движение без массы ничего не учитывает — это пустая строка журнала."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(async_client, headers, fkko_code="46101001513")
        response = await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "generated",
                "happened_on": str(date.today()),
                "quantity_tons": "0",
            },
            headers=headers,
        )
        assert response.status_code == 422

    async def test_движение_в_будущем_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(async_client, headers, fkko_code="43411002295")
        response = await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "transferred",
                "happened_on": str(date.today() + timedelta(days=1)),
                "quantity_tons": "1.000",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "будущем" in response.text

    async def test_чужой_паспорт_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": "no-such-passport",
                "kind": "generated",
                "happened_on": str(date.today()),
                "quantity_tons": "1.000",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Паспорт не найден" in response.text


class TestЛимиты:
    async def test_превышение_лимита_считается_фактом(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Лимит внесён и образование за год его превысило — это факт из данных."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(
            async_client,
            headers,
            fkko_code="30112001294",
            annual_limit_tons="2.000",
        )
        today = date.today()
        await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "generated",
                "happened_on": str(today),
                "quantity_tons": "2.500",
            },
            headers=headers,
        )
        listed = await async_client.get(f"{_API}/waste-passports", headers=headers)
        row = next(r for r in listed.json()["items"] if r["id"] == passport_id)
        assert row["generated_this_year_tons"] == "2.500"
        assert row["over_limit"] is True

    async def test_без_лимита_никакого_суждения_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: лимит платформа не рассчитывает.

        Он берётся из нормативов образования отходов и лимитов на размещение
        (НООЛР) или декларации; без внесённого лимита превышения быть не может
        по построению. Сторож против соблазна «прикинуть лимит» в следующей
        волне.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        passport_id = await _passport(async_client, headers, fkko_code="91910001205")
        await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "generated",
                "happened_on": str(date.today()),
                "quantity_tons": "999.000",
            },
            headers=headers,
        )
        listed = await async_client.get(f"{_API}/waste-passports", headers=headers)
        row = next(r for r in listed.json()["items"] if r["id"] == passport_id)
        assert row["annual_limit_tons"] is None
        assert row["over_limit"] is False


class TestСводкаОтходов:
    async def test_счётчики_отходов_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        passport_id = await _passport(async_client, headers, fkko_code="47110101521")
        await async_client.post(
            f"{_API}/waste-movements",
            json={
                "passport_id": passport_id,
                "kind": "generated",
                "happened_on": str(date.today()),
                "quantity_tons": "5.000",
            },
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["waste_passports"] == before["waste_passports"] + 1
        assert after["waste_movements"] == before["waste_movements"] + 1
        assert after["waste_over_limit"] == before["waste_over_limit"]


class TestИзоляцияАрендатора:
    async def test_чужое_движение_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/waste-movements/does-not-exist",
            json={"quantity_tons": "1.000"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_чужой_паспорт_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/waste-passports/does-not-exist",
            json={"name": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловарьКлассовНаФронте:
    """Срез-99: класс опасности выбирают в форме из копии словаря на фронте.

    Значений ровно четыре, и пятого быть не должно: отходы V класса
    паспортизации не подлежат. Сторож ловит и лишнее значение, и расхождение
    подписей — список формы строится из этого map.
    """

    def test_классы_на_фронте_совпадают_с_бэкендом(self) -> None:
        text = _FRONTEND_ECOLOGY_API.read_text(encoding="utf-8")
        block = re.search(
            r"WASTE_HAZARD_CLASS_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся map WASTE_HAZARD_CLASS_TITLES"
        front = dict(re.findall(r'^\s*([A-Za-z]+):\s*"([^"]+)"', block.group(1), re.M))
        assert front == WASTE_HAZARD_CLASSES, sorted(front.items() ^ WASTE_HAZARD_CLASSES.items())

    def test_виды_движения_на_фронте_совпадают_с_бэкендом(self) -> None:
        """Срез-100: вид движения выбирают в форме журнала из копии словаря.

        Свободная строка сделала бы учёт непересчитываемым, а 2-ТП
        невозможной; поэтому список формы строится из ``WASTE_MOVEMENT_KIND_TITLES``.
        """

        text = _FRONTEND_ECOLOGY_API.read_text(encoding="utf-8")
        block = re.search(
            r"WASTE_MOVEMENT_KIND_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся map WASTE_MOVEMENT_KIND_TITLES"
        front = dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))
        assert front == WASTE_MOVEMENT_KINDS, sorted(front.items() ^ WASTE_MOVEMENT_KINDS.items())


class TestДоговорыОператоров:
    """Срез-112: договоры для выбора в журнале — своя узкая ручка.

    Требование разд. 55.2 «договоры с операторами» упиралось не в данные (поле
    ``contract_id`` у движения есть со среза-2), а в ДОСТУП: ядровой реестр
    ``/contracts`` закрыт ролями бухгалтерии и отдаёт суммы. Эколог должен
    выбрать договор, а не читать финансовые условия.
    """

    async def test_без_выдачи_модуля_ручки_нет(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/waste-contracts", headers=headers)
        assert response.status_code == 404

    async def test_отдаёт_контрагента_без_сумм(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            session.add(
                Contract(
                    tenant_id=str(tenant.id),
                    company_id=company.id,
                    title="Вывоз отходов IV класса",
                    counterparty_name="ООО «Оператор»",
                    contract_number="ОТХ-12",
                    status=ContractStatus.ACTIVE,
                    valid_until=date.today() + timedelta(days=200),
                    total_amount=1_250_000,
                    currency="RUB",
                )
            )
            await session.commit()

        response = await async_client.get(f"{_API}/waste-contracts", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["counterparty_name"] == "ООО «Оператор»"
        assert item["contract_number"] == "ОТХ-12"
        assert item["status"] == "active"
        # Финансовых условий тут нет и быть не должно: выбирают договор, а не
        # читают сумму (ядровая ручка не зря закрыта ролями бухгалтерии).
        assert "total_amount" not in item
        assert "currency" not in item

    async def test_чужой_арендатор_договоров_не_видит(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        async with sessionmaker() as session:
            other = await data_factory.ensure_tenant(slug="other", session=session)
            company = await data_factory.create_company(
                tenant=other, name="Чужая компания", session=session
            )
            session.add(
                Contract(
                    tenant_id=str(other.id),
                    company_id=company.id,
                    title="Чужой договор",
                    counterparty_name="ООО «Чужой оператор»",
                    status=ContractStatus.ACTIVE,
                    currency="RUB",
                )
            )
            await session.commit()

        response = await async_client.get(f"{_API}/waste-contracts", headers=headers)

        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0
