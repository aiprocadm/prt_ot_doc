"""Контур ПБ срез-6 (Доп. №1 разд. 54.1): документы пожарной безопасности.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. ТЗ требует учитывать «приказы, инструкции о
мерах ПБ (общеобъектовые и по помещениям), планы эвакуации, регламенты,
декларацию ПБ, журналы». В платформе было только ВЫПУСКАНИЕ пяти бумаг
пожарным комплектом документной фабрики — и ни одного места, где видно, какие
документы ПБ у объекта ЕСТЬ и не пора ли их пересматривать.

Ядровой ``Document`` для этого не годится ПО ПОСТРОЕНИЮ, а не по вкусу:
* ``Document.template_id`` — NOT NULL, поэтому документ, который платформа не
  выпускала (декларация, поданная в МЧС; план эвакуации, нарисованный
  подрядчиком), в реестр ядра не заводится вовсе;
* вида документа у ядра нет — «тип» выводится из свободной строки
  ``Template.domain``;
* срока пересмотра у ядра нет ни одного поля.

Поэтому дисциплина заводит СВОЮ учётную карточку — ровно то, чего в ядре нет,
— и переиспользует ядро там, где оно есть: ссылка на выпущенный фабрикой
``Document`` и ЕДИНЫЙ словарь состояний срока (``ContingentItemStatus``:
ok / due_soon / overdue). Сам классификатор НЕ импортируется: гард границ
контекстов (ARCH-3) запрещает ``app.modules.* -> app.domains.*``, и три таких
импорта у подрядчиков и СИЗ числятся в списке ДОЛГА, а не образцом — заводить
четвёртую запись долга ради четырёх строк правила неверно.

ГРАНИЦА, названная и здесь, и на экране: платформа НЕ объявляет, какие
документы объекту обязательны. Декларация ПБ обязательна не для всех объектов,
план эвакуации — не для всех этажей; признаков применимости в данных нет.
Считается то, что следует из данных: что заведено и что просрочено по
пересмотру. Тот же довод, что у интервала тренировок (срез-4).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.fire_safety import FIRE_DOCUMENT_KINDS
from app.models.models import Tenant

_FRONTEND_FIRE_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "fireSafety.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/fireSafety.ts``."""

    text = _FRONTEND_FIRE_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))


pytestmark = pytest.mark.anyio

_API = "/api/v1/fire-safety"


async def _grant(sessionmaker, code: str = "fire_safety", on: bool = True) -> None:
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


class TestРеестрДокументов:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/documents", headers=headers)
        assert response.status_code == 404

    async def test_документ_заводится_и_состояние_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "order",
                "title": "О противопожарном режиме",
                "number": "17-ПБ",
                "approved_on": str(today - timedelta(days=30)),
                "review_due": str(today + timedelta(days=300)),
                "responsible": "Инженер по ОТ и ПБ Смирнов",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["kind_label"] == "Приказ"
        assert body["status"] == "ok"
        assert body["status_label"] == "Действует"

    async def test_общеобъектовая_и_по_помещению_различаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ТЗ прямо требует «общеобъектовые И по помещениям» — это разные виды.

        Одним видом их не выразить: общеобъектовая инструкция одна на объект, а
        по помещениям их столько, сколько помещений, и проверяющий смотрит
        именно наличие второй у пожароопасных помещений.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        general = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "instruction_general",
                "title": "Инструкция о мерах пожарной безопасности",
            },
            headers=headers,
        )
        assert general.status_code == 201, general.text
        assert general.json()["kind_label"] == "Инструкция о мерах ПБ (общеобъектовая)"

        room = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "instruction_room",
                "title": "Инструкция для склада ЛКМ",
                "location": "Склад ЛКМ, корпус Б",
            },
            headers=headers,
        )
        assert room.status_code == 201, room.text
        assert room.json()["kind_label"] == "Инструкция о мерах ПБ (по помещению)"
        assert room.json()["location"] == "Склад ЛКМ, корпус Б"

    async def test_все_виды_из_ТЗ_принимаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Перечень ТЗ закрыт целиком: приказы, инструкции, планы эвакуации,
        регламенты, декларация ПБ, журналы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for kind in (
            "order",
            "instruction_general",
            "instruction_room",
            "evacuation_plan",
            "regulation",
            "declaration",
            "journal",
        ):
            response = await async_client.post(
                f"{_API}/documents",
                json={"kind": kind, "title": f"Документ {kind}"},
                headers=headers,
            )
            assert response.status_code == 201, f"{kind}: {response.text}"

    async def test_неизвестный_вид_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/documents",
            json={"kind": "справка", "title": "Что-то"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный вид документа" in response.text


class TestСрокПересмотра:
    async def test_просроченный_пересмотр_назван_просроченным(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        response = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "instruction_general",
                "title": "Инструкция 2019 года",
                "review_due": str(today - timedelta(days=1)),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "overdue"
        assert response.json()["status_label"] == "Просрочен пересмотр"

    async def test_скорый_пересмотр_виден_заранее(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Тот же горизонт 30 дней, что у остальной готовности к проверке."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "regulation",
                "title": "Регламент ТО систем",
                "review_due": str(date.today() + timedelta(days=10)),
            },
            headers=headers,
        )
        assert response.json()["status"] == "due_soon"

    async def test_без_срока_документ_считается_бессрочным(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ядровое правило без даты отвечает MISSING, но у ДОКУМЕНТА пустой
        срок пересмотра означает «бессрочный», а не «отсутствует».

        Прецедент — реестр документов подрядчиков (document_expiry_status):
        там сделан ровно такой же выбор. Иначе приказ без даты пересмотра
        показывался бы как отсутствующий документ, которого нет, — при том что
        он есть и лежит в реестре.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/documents",
            json={"kind": "journal", "title": "Журнал эксплуатации систем ПБ"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "ok"
        assert response.json()["review_due"] is None

    async def test_пересмотр_переносится_правкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "order",
                "title": "Приказ о назначении ответственного",
                "review_due": str(today - timedelta(days=5)),
            },
            headers=headers,
        )
        patched = await async_client.patch(
            f"{_API}/documents/{created.json()['id']}",
            json={"review_due": str(today + timedelta(days=365))},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status"] == "ok"


class TestГотовностьКПроверке:
    async def test_просроченные_документы_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "declaration",
                "title": "Декларация пожарной безопасности",
                "review_due": str(today - timedelta(days=2)),
            },
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["overdue_documents"] == before["overdue_documents"] + 1
        assert after["fire_documents"] == before["fire_documents"] + 1

    async def test_обязательность_не_выдумывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: платформа не объявляет, какие документы объекту обязательны.

        Декларация ПБ обязательна не для всех объектов, план эвакуации — не для
        всех этажей; признаков применимости в данных нет. Сторож против
        соблазна дописать в сводку «не хватает N обязательных документов» в
        следующей волне: у пустого реестра просрочек НОЛЬ, а не «всё пропало».
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["overdue_documents"] == 0
        assert "missing_documents" not in body
        assert "required_documents" not in body


class TestИзоляцияАрендатора:
    async def test_чужая_площадка_не_подтверждается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/documents",
            json={
                "kind": "order",
                "title": "Приказ",
                "site_id": "no-such-site",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Площадка не найдена" in response.text

    async def test_чужой_документ_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/documents/does-not-exist",
            json={"title": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловарьВидовДокументовНаФронте:
    """Срез-103: вид документа выбирают в форме из копии словаря на фронте.

    Список формы строится из ``FIRE_DOCUMENT_KIND_TITLES`` в ``api/fireSafety.ts``:
    вид, добавленный только на бэкенде, нельзя было бы ни выбрать, ни прочитать
    словами. Тот же приём, что у видов сроков экологии (срез-98).
    """

    def test_виды_документов_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("FIRE_DOCUMENT_KIND_TITLES")
        assert front == FIRE_DOCUMENT_KINDS, sorted(front.items() ^ FIRE_DOCUMENT_KINDS.items())
