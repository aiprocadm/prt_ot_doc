"""Контур ГО и ЧС срез-4 (Доп. №1 разд. 56.1): категорирование и планирование.

Требование: «Категорирование и планирование: сведения по ГО, паспорт
безопасности объекта, планы ГО и действий по предупреждению/ликвидации ЧС» и
частично «Документы и отчётность: приказы, положения, инструкции».

СВЕРКА нашла расхождение, которое три предыдущих среза обходили молча:

**Категория объекта по ГО нигде не хранится, но у специалиста её СПРАШИВАЮТ.**
В мастере комплекта GOCHS_BASE есть вопрос ``facility_category`` («Категория
объекта по ГО») — то есть при каждом выпуске пакета документов человек вводит
одно и то же руками, и введённое никуда не сохраняется. При этом ГРАНИЦЫ
срезов 1–3 трижды ссылались на эту категорию («сколько формирований нужно —
следует из категории организации по ГО», «периодичность учений зависит от
категории», «обязана ли организация создавать КЧС — следует из категории»), а
хранить её было негде. Требование «сведения по ГО» ровно об этом.

Решения:

* **сведения по ГО — на площадку, одна карточка на объект.** Категорирование
  присваивается объекту, а не абстрактной организации; вторая карточка на тот
  же объект означала бы два разных решения о категорировании, чего не бывает;
* **категория — ЗАКРЫТЫЙ словарь из четырёх** (особой важности, первая,
  вторая, без категории): перечень установлен постановлением Правительства,
  пятой категории не существует. «Без категории» — ЗНАЧЕНИЕ, а не пустота:
  «объекту категория не присвоена» и «сведения не внесены» — разные вещи;
* **документы планирования — своя учётная карточка**, как у ПБ: ядровой
  ``Document`` требует ``template_id``, поэтому план ГО, утверждённый до
  внедрения платформы, или паспорт безопасности, согласованный в органе, в
  реестр ядра не заводятся вовсе. Ссылка на выпущенный фабрикой документ
  сохраняется, когда он есть;
* **пустой срок пересмотра = БЕССРОЧНО, а не «просрочено»** (дословно решение
  реестра документов ПБ и подрядчиков).

ГРАНИЦА: платформа НЕ присваивает категорию и НЕ выводит из неё обязанности.
Категорирование выполняет орган по показателям (численность работающих,
оборонное значение, опасные производства), которых в системе нет. Полей
«предлагаемая категория», «требуемые планы» и «соответствует ли объект» нет.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.civil_defense import CD_DOCUMENT_KINDS, CD_GO_CATEGORIES
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Company, Site, Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/civil-defense"


_FRONTEND_CD_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "civilDefense.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/civilDefense.ts``."""

    text = _FRONTEND_CD_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_0-9]+):\s*"([^"]+)"', block.group(1), re.M))


async def _grant(sessionmaker, code: str = "civil_defense", on: bool = True) -> None:
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


async def _site(sessionmaker, name: str = "Производственная площадка") -> str:
    """Площадка из ЯДРА: дисциплина своих объектов не заводит."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = (
            await session.execute(
                select(Company).where(Company.tenant_id == tenant.id)
            )
        ).scalars().first()
        if company is None:
            company = Company(tenant_id=tenant.id, name="Головная компания")
            session.add(company)
            await session.flush()
        site = Site(tenant_id=tenant.id, company_id=company.id, name=name)
        session.add(site)
        await session.commit()
        return str(site.id)


async def _profile(
    async_client,
    headers,
    site_id: str,
    *,
    category: str = "second",
    decision_number: str | None = None,
) -> dict:
    payload: dict[str, object] = {"site_id": site_id, "category": category}
    if decision_number is not None:
        payload["decision_number"] = decision_number
    response = await async_client.post(
        f"{_API}/profiles", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _document(
    async_client,
    headers,
    *,
    kind: str = "plan_go",
    title: str = "План гражданской обороны",
    review_due: date | None = None,
    site_id: str | None = None,
) -> dict:
    payload: dict[str, object] = {"kind": kind, "title": title}
    if review_due is not None:
        payload["review_due"] = str(review_due)
    if site_id is not None:
        payload["site_id"] = site_id
    response = await async_client.post(
        f"{_API}/documents", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestСведенияПоГО:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/profiles", headers=headers)
        assert response.status_code == 404

    async def test_категория_заводится_и_читается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker)
        body = await _profile(
            async_client,
            headers,
            site_id,
            category="first",
            decision_number="Решение КЧС от 12.03.2025 №14",
        )
        assert body["category_label"] == "Первая категория по ГО"
        assert body["site_id"] == site_id

    async def test_без_категории_это_значение_а_не_пустота(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Категория не присвоена» и «сведения не внесены» — разные вещи."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker, "Склад")
        body = await _profile(async_client, headers, site_id, category="none")
        assert body["category"] == "none"
        assert body["category_label"] == "Категория не присвоена"

    async def test_неизвестная_категория_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Пятой категории по ГО не существует."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker, "Цех")
        response = await async_client.post(
            f"{_API}/profiles",
            json={"site_id": site_id, "category": "пятая"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_вторая_карточка_на_ту_же_площадку_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Два решения о категорировании одного объекта не бывает."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker, "Котельная")
        await _profile(async_client, headers, site_id)
        response = await async_client.post(
            f"{_API}/profiles",
            json={"site_id": site_id, "category": "first"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_карточка_на_другой_площадке_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first = await _site(sessionmaker, "Площадка А")
        second = await _site(sessionmaker, "Площадка Б")
        await _profile(async_client, headers, first)
        await _profile(async_client, headers, second, category="none")

    async def test_чужая_площадка_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/profiles",
            json={
                "site_id": "00000000-0000-0000-0000-000000000000",
                "category": "second",
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text

    async def test_категорию_можно_пересмотреть(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Орган пересматривает решение — карточка обязана это принять."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker, "Площадка В")
        profile = await _profile(async_client, headers, site_id, category="none")
        patched = await async_client.patch(
            f"{_API}/profiles/{profile['id']}",
            json={"category": "special", "decision_number": "№ 7"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["category_label"] == "Объект особой важности"


class TestДокументыПланирования:
    async def test_план_го_заводится_с_видом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _document(async_client, headers)
        assert body["kind_label"] == "План гражданской обороны"
        # Пустой срок пересмотра — БЕССРОЧНО, а не просрочка.
        assert body["review_status"] == "ok"
        assert body["review_due"] is None

    async def test_все_виды_из_требования_приняты(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Планы, паспорт безопасности, приказы, положения, инструкции."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for kind in (
            "plan_go",
            "plan_emergency",
            "safety_passport",
            "order",
            "regulation",
            "instruction",
        ):
            await _document(async_client, headers, kind=kind, title=f"Документ {kind}")

    async def test_неизвестный_вид_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/documents",
            json={"kind": "записка", "title": "Что-то"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_просроченный_пересмотр_назван_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _document(
            async_client,
            headers,
            kind="plan_emergency",
            title="План действий по предупреждению и ликвидации ЧС",
            review_due=date.today() - timedelta(days=5),
        )
        listed = await async_client.get(f"{_API}/documents", headers=headers)
        item = listed.json()["items"][0]
        assert item["review_status"] == "overdue"
        assert item["review_status_label"] == "Просрочен пересмотр"

    async def test_близкий_срок_пересмотра_назван_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _document(
            async_client,
            headers,
            kind="safety_passport",
            title="Паспорт безопасности объекта",
            review_due=date.today() + timedelta(days=10),
        )
        listed = await async_client.get(f"{_API}/documents", headers=headers)
        assert listed.json()["items"][0]["review_status"] == "due_soon"

    async def test_документ_можно_привязать_к_площадке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker, "Площадка Г")
        body = await _document(async_client, headers, site_id=site_id)
        assert body["site_id"] == site_id

    async def test_документ_без_площадки_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """План ГО организации не привязан к одному объекту."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _document(async_client, headers, kind="order", title="Приказ")
        assert body["site_id"] is None


class TestСводкаИГраница:
    async def test_сводка_считает_категории_и_просрочки_пересмотра(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first = await _site(sessionmaker, "Объект 1")
        second = await _site(sessionmaker, "Объект 2")
        await _profile(async_client, headers, first, category="second")
        await _profile(async_client, headers, second, category="none")
        await _document(
            async_client,
            headers,
            review_due=date.today() - timedelta(days=1),
        )
        await _document(async_client, headers, kind="order", title="Приказ")

        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        body = readiness.json()
        assert body["profiles_total"] == 2
        assert body["profiles_by_category"]["second"] == 1
        assert body["profiles_by_category"]["none"] == 1
        assert body["planning_documents"] == 2
        assert body["planning_review_overdue"] == 1

    async def test_платформа_не_присваивает_категорию(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: категорирование делает орган по показателям, которых нет."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site_id = await _site(sessionmaker, "Объект границы")
        body = await _profile(async_client, headers, site_id)
        forbidden = {
            "suggested_category",
            "recommended_category",
            "required_documents",
            "compliance",
        }
        assert forbidden.isdisjoint(body.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())

    async def test_чужая_карточка_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/profiles/00000000-0000-0000-0000-000000000000",
            json={"category": "first"},
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestСловариПланированияНаФронте:
    """Срез-110: категорию по ГО и вид документа выбирают из копий словарей.

    «Категория не присвоена» — полноценное значение словаря, а не пустое
    поле: пропади оно из формы, специалисту нечем было бы ответить «решения
    ещё нет», и он выбрал бы чужую категорию.
    """

    def test_категории_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("CD_GO_CATEGORY_TITLES")
        assert front == CD_GO_CATEGORIES, sorted(
            front.items() ^ CD_GO_CATEGORIES.items()
        )

    def test_виды_документов_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("CD_DOCUMENT_KIND_TITLES")
        assert front == CD_DOCUMENT_KINDS, sorted(
            front.items() ^ CD_DOCUMENT_KINDS.items()
        )

