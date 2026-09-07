"""Контур БДД срез-2 (Доп. №1 разд. 56.2): водители.

Требование: «Водители: водительский состав, стаж/категории, режим труда и
отдыха, нарушения». Этот срез закрывает состав, стаж и категории; режим труда
и отдыха и нарушения — следующий срез, они опираются на путевые листы.

СВЕРКА нашла:

1. **Водителей в продукте нет вовсе.** После среза-1 в контуре БДД есть только
   транспортные средства. Ни карточки водителя, ни удостоверения, ни допуска —
   при этом комплект документов БДД уже ПЕЧАТАЕТ «режим труда и отдыха
   водителей» и «ответственного за БДД» свободным текстом: бумага оформляется,
   а учёта за ней нет. Тот же признак, что был у тренировок по пожарной
   безопасности в разд. 54.1.
2. **Ядро утверждало «Поимённый учёт БДД в системе не ведётся».** Этот срез
   делает утверждение ложным в тот же день. Оставить его значило бы повторить
   дрейф, который срез-1 нашёл у причины для ГО и ЧС: причина обязана
   называть свойство модели, а не перечень таблиц.

Решения:

* **человек НЕ дублируется**: карточка ссылается на ядрового ``Person``, ФИО и
  должность приходят из него. Второй список сотрудников разошёлся бы с первым
  на первой же кадровой правке (прецедент аттестаций разд. 54.2 и формирований
  разд. 56.1);
* **один человек — одна карточка**, один номер удостоверения — одна карточка:
  дубль это ошибка ввода, а не второй водитель;
* **категории — ЗАКРЫТЫЙ словарь** (ФЗ-196 ст. 25), а не свободная строка:
  «B», «в» и «кат. B» — три разные строки об одном, и вопрос «кто допущен к
  автобусу» остался бы без ответа (прецедент вида инструктажа разд. 54.1);
* **СТАЖ СЧИТАЕТСЯ ПРИ ЧТЕНИИ от даты начала и не хранится числом**:
  записанное «стаж 3 года» через два года молча становится ложью, а отличить
  устаревшее число от верного нельзя — у числа нет даты, на которую оно верно;
* **пустой срок удостоверения = «сведений нет», а не «бессрочно»** и не
  «просрочено» (как у полиса и диагностической карты в срезе-1);
* **просрочки — только по ДОПУЩЕННЫМ**: у отстранённого водителя просроченное
  удостоверение это шум, а не проблема (как у списанного ТС).

ГРАНИЦА: платформа НЕ решает, какая категория нужна для конкретной машины и
достаточен ли стаж для перевозки пассажиров. Это следует из массы ТС, числа
мест и вида перевозок по закону — таких данных в системе нет. Полей «допущен
ли к этой машине», «хватает ли стажа» и «соответствует ли водитель» нет ни в
записи, ни в сводке.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, EmploymentStatus, Person
from app.models.models import Tenant
from app.models.road_safety import DRIVER_LICENSE_CATEGORIES, DRIVER_STATUSES

pytestmark = pytest.mark.anyio

_API = "/api/v1/road-safety"


_FRONTEND_ROAD_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "roadSafety.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/roadSafety.ts``."""

    text = _FRONTEND_ROAD_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_0-9]+):\s*"([^"]+)"', block.group(1), re.M))


async def _grant(sessionmaker, code: str = "road_safety", on: bool = True) -> None:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
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
            session.add(
                FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on)
            )
        else:
            grant.on = on
        await session.commit()


async def _person(sessionmaker, last_name: str = "Шофёров", **extra) -> str:
    """Человек из ЯДРА: карточка водителя своих людей не заводит."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = (
            (
                await session.execute(
                    select(Company).where(Company.tenant_id == tenant.id)
                )
            )
            .scalars()
            .first()
        )
        if company is None:
            company = Company(tenant_id=tenant.id, name="Головная компания")
            session.add(company)
            await session.flush()
        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            last_name=last_name,
            first_name="Пётр",
            middle_name="Иванович",
            personnel_number=f"ТН-{last_name}",
            position_title="Водитель",
            **extra,
        )
        session.add(person)
        await session.commit()
        return str(person.id)


async def _driver(
    async_client,
    headers,
    person_id: str,
    *,
    license_number: str = "9900 123456",
    categories: list[str] | None = None,
    license_due: date | None = None,
    experience_since: date | None = None,
    status: str = "admitted",
) -> dict:
    payload: dict[str, object] = {
        "person_id": person_id,
        "license_number": license_number,
        "categories": categories or ["B", "C"],
        "status": status,
    }
    if license_due is not None:
        payload["license_due"] = str(license_due)
    if experience_since is not None:
        payload["experience_since"] = str(experience_since)
    response = await async_client.post(f"{_API}/drivers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestВодительскийСостав:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/drivers", headers=headers)
        assert response.status_code == 404

    async def test_карточка_берёт_человека_из_ядра(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ФИО и должность приходят из ``Person``, а не хранятся в карточке."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        body = await _driver(async_client, headers, person_id)
        assert body["person_name"] == "Шофёров Пётр Иванович"
        assert body["position_title"] == "Водитель"
        assert body["status_label"] == "Допущен к управлению"

    async def test_категории_приходят_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        body = await _driver(async_client, headers, person_id, categories=["D"])
        assert body["categories"] == ["D"]
        assert body["category_labels"] == ["D — автобусы"]

    async def test_неизвестная_категория_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Главный сторож словаря: свободная строка сделала бы контроль
        невыполнимым — «B», «в» и «кат. B» это три разные строки об одном."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9900 000001",
                "categories": ["Б"],
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_без_единой_категории_карточка_не_заводится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9900 000002",
                "categories": [],
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_неизвестный_допуск_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9900 000003",
                "categories": ["B"],
                "status": "в отпуске навсегда",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_вторая_карточка_тому_же_человеку_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Иначе у одного человека два разных срока удостоверения — и какой
        из них правда, неизвестно."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        await _driver(async_client, headers, person_id, license_number="9900 111111")
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9900 222222",
                "categories": ["B"],
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_дубль_номера_удостоверения_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first = await _person(sessionmaker, last_name="Первов")
        second = await _person(sessionmaker, last_name="Второв")
        await _driver(async_client, headers, first, license_number="9900 333333")
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": second,
                "license_number": "9900 333333",
                "categories": ["B"],
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_несуществующий_человек_даёт_404(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": "00000000-0000-0000-0000-000000000000",
                "license_number": "9900 444444",
                "categories": ["B"],
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text

    async def test_отстранение_меняет_допуск_а_не_удаляет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        driver = await _driver(
            async_client, headers, person_id, license_number="9900 555555"
        )
        patched = await async_client.patch(
            f"{_API}/drivers/{driver['id']}",
            json={"status": "suspended"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status_label"] == "Отстранён"

        listing = await async_client.get(f"{_API}/drivers", headers=headers)
        assert listing.json()["total"] == 1, "карточка обязана остаться в истории"

    async def test_чужая_карточка_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/drivers/00000000-0000-0000-0000-000000000000",
            json={"status": "suspended"},
            headers=headers,
        )
        assert response.status_code == 404, response.text

    async def test_отбор_по_категории(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        bus = await _person(sessionmaker, last_name="Автобусов")
        truck = await _person(sessionmaker, last_name="Грузовиков")
        await _driver(
            async_client, headers, bus, license_number="9900 666666", categories=["D"]
        )
        await _driver(
            async_client,
            headers,
            truck,
            license_number="9900 777777",
            categories=["B", "C"],
        )
        response = await async_client.get(
            f"{_API}/drivers", params={"category": "D"}, headers=headers
        )
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["person_name"].startswith("Автобусов")

    async def test_отбор_по_человеку(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Срез-67: строка «БДД» карточки сотрудника открывает состав НА НЁМ."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        bus = await _person(sessionmaker, last_name="Автобусов")
        truck = await _person(sessionmaker, last_name="Грузовиков")
        await _driver(
            async_client, headers, bus, license_number="9900 666666", categories=["D"]
        )
        await _driver(
            async_client,
            headers,
            truck,
            license_number="9900 777777",
            categories=["B", "C"],
        )
        response = await async_client.get(
            f"{_API}/drivers", params={"person_id": truck}, headers=headers
        )
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["person_id"] == truck
        # Чужой/несуществующий человек — пусто, а не весь состав.
        nobody = await async_client.get(
            f"{_API}/drivers", params={"person_id": "no-such-person"}, headers=headers
        )
        assert nobody.json()["total"] == 0


class TestСтаж:
    """Стаж СЧИТАЕТСЯ, а не хранится: у числа нет даты, на которую оно верно."""

    async def test_стаж_считается_от_даты_начала(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        # ровно три года и один день назад — стаж три полных года
        since = date.today() - timedelta(days=365 * 3 + 2)
        body = await _driver(
            async_client,
            headers,
            person_id,
            license_number="9900 888888",
            experience_since=since,
        )
        assert body["experience_years"] == 3
        assert body["experience_since"] == str(since)

    async def test_стаж_числом_задать_нельзя(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож решения: присланное число лет не должно попадать в запись —
        иначе оно застынет и разойдётся с датой."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9900 999999",
                "categories": ["B"],
                "experience_since": str(date.today() - timedelta(days=400)),
                "experience_years": 30,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["experience_years"] == 1, "стаж считает сервер"

    async def test_стаж_без_даты_не_выдумывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        body = await _driver(
            async_client, headers, person_id, license_number="9901 000001"
        )
        assert body["experience_years"] is None, "«не знаем» — это не «ноль лет»"

    async def test_стаж_из_будущего_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        response = await async_client.post(
            f"{_API}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9901 000002",
                "categories": ["B"],
                "experience_since": str(date.today() + timedelta(days=1)),
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text


class TestСрокУдостоверения:
    async def test_пустой_срок_это_сведений_нет_а_не_просрочено(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """У водительского удостоверения бессрочности не бывает, но «мы не
        знаем» и «истекло» — разные утверждения."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        body = await _driver(
            async_client, headers, person_id, license_number="9901 000003"
        )
        assert body["license_status"] == "missing"
        assert body["license_status_label"] == "Сведения не внесены"

    async def test_истёкшее_удостоверение_просрочено(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        body = await _driver(
            async_client,
            headers,
            person_id,
            license_number="9901 000004",
            license_due=date.today() - timedelta(days=10),
        )
        assert body["license_status"] == "overdue"


class TestСводкаПоВодителям:
    async def test_просрочки_только_по_допущенным(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        admitted = await _person(sessionmaker, last_name="Допущенов")
        suspended = await _person(sessionmaker, last_name="Отстранённов")
        await _driver(
            async_client,
            headers,
            admitted,
            license_number="9902 000001",
            license_due=date.today() - timedelta(days=5),
        )
        second = await _driver(
            async_client,
            headers,
            suspended,
            license_number="9902 000002",
            license_due=date.today() - timedelta(days=500),
        )
        await async_client.patch(
            f"{_API}/drivers/{second['id']}",
            json={"status": "suspended"},
            headers=headers,
        )

        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["total_drivers"] == 2
        assert body["drivers_by_status"]["admitted"] == 1
        assert body["drivers_by_status"]["suspended"] == 1
        assert body["driver_license_overdue"] == 1, "отстранённый в просрочки не идёт"

    async def test_сводка_считает_допущенных_без_срока(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        without = await _person(sessionmaker, last_name="Безсрокова")
        with_due = await _person(sessionmaker, last_name="Сосроком")
        await _driver(async_client, headers, without, license_number="9902 000003")
        await _driver(
            async_client,
            headers,
            with_due,
            license_number="9902 000004",
            license_due=date.today() + timedelta(days=300),
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["driver_license_missing"] == 1

    async def test_уволенный_в_просрочки_не_идёт_а_в_составе_остаётся(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Уволенный не в счёт» (BIZ-54-57 срез-95): тот же довод, что у
        отстранённого, — карточка в составе цела, а её удостоверение,
        просроченное или невнесённое, проблемой не считается."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        here = await _person(sessionmaker, last_name="Работающий")
        gone = await _person(
            sessionmaker,
            last_name="Уволенный",
            employment_status=EmploymentStatus.TERMINATED,
        )
        erased = await _person(sessionmaker, last_name="Удалённый")
        await _driver(
            async_client,
            headers,
            here,
            license_number="9902 000011",
            license_due=date.today() - timedelta(days=5),
        )
        await _driver(
            async_client,
            headers,
            gone,
            license_number="9902 000012",
            license_due=date.today() - timedelta(days=5),
        )
        await _driver(async_client, headers, erased, license_number="9902 000013")
        # Карточку удалённому не завести (PERSON_NOT_FOUND) — удаляем после.
        async with sessionmaker() as session:
            person = await session.get(Person, erased)
            person.deleted_at = datetime.now(timezone.utc)
            await session.commit()

        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["total_drivers"] == 3, "состав — реестр, история цела"
        assert body["drivers_by_status"]["admitted"] == 3
        assert body["driver_license_overdue"] == 1, "уволенный в просрочки не идёт"
        assert body["driver_license_missing"] == 0, "удалённый — тоже"

    async def test_платформа_не_решает_допуск_к_машине_и_хватает_ли_стажа(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: это следует из массы ТС, числа мест и вида перевозок."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker)
        body = await _driver(
            async_client, headers, person_id, license_number="9902 000005"
        )
        forbidden = {
            "can_drive",
            "allowed_vehicle_kinds",
            "compliant",
            "experience_enough",
            "required_categories",
        }
        assert forbidden.isdisjoint(body.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())


class TestПричинаДисциплиныБДД:
    """Починка собственного дрейфа, найденная сверкой этого среза.

    Ядро утверждало «Поимённый учёт БДД в системе не ведётся» — этот срез
    делает утверждение ложным. Причина обязана называть свойство модели (нет
    эталона, не с чем сравнивать), а не отсутствие записей: перечень таблиц
    протухает за один срез, свойство модели — нет.
    """

    def test_причина_не_отрицает_поимённый_учёт(self) -> None:
        from app.core.disciplines import UNMEASURED_DISCIPLINES, Discipline

        reason = UNMEASURED_DISCIPLINES[Discipline.ROAD_SAFETY].lower()
        assert "поимённый учёт бдд" not in reason
        assert "эталон" in reason, "причина обязана называть, чего именно нет"

    def test_бдд_остаётся_без_светофора(self) -> None:
        """Реестр водителей — ещё не эталон: норм по должностям в системе нет,
        и красить дисциплину зелёным было бы выдумкой. (Срез-64: истекшее или
        истекающее удостоверение — факт, он красит красным/жёлтым, но
        измеримой дисциплину не делает — сторож ``tests/test_road_safety_status.py``.)"""

        from app.core.disciplines import (
            MEASURED_DISCIPLINES,
            UNMEASURED_DISCIPLINES,
            Discipline,
        )

        assert Discipline.ROAD_SAFETY not in MEASURED_DISCIPLINES
        assert Discipline.ROAD_SAFETY in UNMEASURED_DISCIPLINES


class TestСловариВодителейНаФронте:
    """Срез-107: категории и допуск выбирают в форме из копий словарей.

    Категории в форме — отметки, и их список строится из
    ``DRIVER_LICENSE_CATEGORY_TITLES``: категория, добавленная только на
    бэкенде, стала бы недоступна для выбора вовсе.
    """

    def test_категории_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("DRIVER_LICENSE_CATEGORY_TITLES")
        assert front == DRIVER_LICENSE_CATEGORIES, sorted(
            front.items() ^ DRIVER_LICENSE_CATEGORIES.items()
        )

    def test_состояния_допуска_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("DRIVER_STATUS_TITLES")
        assert front == DRIVER_STATUSES, sorted(front.items() ^ DRIVER_STATUSES.items())

