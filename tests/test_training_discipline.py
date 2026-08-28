"""Разметка учебных программ дисциплинами (Доп. №1 разд. 56.1 + кросс-контур).

Требование 56.1: «Обучение и учения: программы обучения по ГО и ЧС, курсовое
обучение, план-график учений и тренировок, журналы». План-график учений закрыт
срезом-2 контура ГО; здесь закрывается «программы обучения по ГО».

СВЕРКА. Контур обучения в ядре ЕСТЬ ЦЕЛИКОМ: программы (``TrainingCourse``),
планы обучения по должностям, занятия (``TrainingSession``) и записи
слушателей — то есть и «курсовое обучение», и «журналы» из требования. Не
хватало ОДНОГО: **у программы нет отнесения к дисциплине**. Курс «Курсовое
обучение по ГО» неотличим от курса по охране труда, и вопрос «какие программы
обучения по ГО заведены» не имел ответа в данных.

Дыра КРОСС-ДИСЦИПЛИНАРНАЯ, а не только про ГО: ровно так же неотличимы
пожарно-технический минимум, обучение по обращению с отходами и подготовка по
промбезопасности. Поэтому размечается САМ КУРС, а контур дисциплины лишь
показывает свою часть — реестр остаётся в ядре (принцип «ядро не дублируется»).

Решения:

* **разметка полем курса, а не отдельным словарём видов.** У инструктажей
  дисциплина выводится из вида (``BRIEFING_TYPE_DISCIPLINE``), потому что вид
  там — закрытый словарь. У программы вида нет вовсе: название свободное,
  поэтому дисциплина хранится прямо у курса;
* **словарь дисциплин — ОБЩИЙ** (``app.core.disciplines.Discipline``), а не
  своя копия: две копии словаря дисциплин разъедутся при первой же новой
  дисциплине. Сторож проверяет, что копии не завелось;
* **пустая дисциплина ЗАКОННА и означает «не размечено»**, а НЕ «общая охрана
  труда»: приписывать незаряженной записи принадлежность — то же враньё, что и
  у инструктажей с неизвестным видом (``discipline_of_briefing`` возвращает
  ``None`` ровно с этим доводом);
* **контур ГО показывает свою часть, но реестром не владеет**: сводка ГО
  считает программы по своей дисциплине, а заводятся и правятся они в разделе
  обучения.

ГРАНИЦА: платформа НЕ назначает дисциплину программе и НЕ требует наличия
программ. Какие программы обучения нужны организации, определяют категория по
ГО, вид деятельности и решения органа — этих данных в системе нет.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_TRAINING_API = "/api/v1/training"
_CD_API = "/api/v1/civil-defense"


async def _grant(sessionmaker, code: str, on: bool = True) -> None:
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


async def _course(
    async_client,
    headers,
    *,
    title: str = "Курсовое обучение по ГО",
    discipline: str | None = "civil_defense",
) -> dict:
    payload: dict[str, object] = {"title": title, "duration_hours": 16}
    if discipline is not None:
        payload["discipline"] = discipline
    response = await async_client.post(
        f"{_TRAINING_API}/courses", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestРазметкаПрограммы:
    async def test_программа_заводится_с_дисциплиной_словами(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        body = await _course(async_client, headers)
        assert body["discipline"] == "civil_defense"
        assert body["discipline_label"] == "ГО и ЧС"

    async def test_программа_без_дисциплины_законна(
        self, async_client, make_auth_headers
    ) -> None:
        """Пусто — «не размечено», а НЕ «общая охрана труда»."""

        headers = await make_auth_headers()
        body = await _course(
            async_client, headers, title="Обучение по охране труда", discipline=None
        )
        assert body["discipline"] is None
        assert body["discipline_label"] is None

    async def test_неизвестная_дисциплина_отвергается(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.post(
            f"{_TRAINING_API}/courses",
            json={"title": "Курс", "discipline": "гражданская_оборона"},
            headers=headers,
        )
        # 400 — собственная конвенция модуля обучения (_training_bad_request),
        # а не 422 контуров дисциплин: единообразие ВНУТРИ модуля важнее.
        assert response.status_code == 400, response.text

    async def test_разметку_можно_поменять(
        self, async_client, make_auth_headers
    ) -> None:
        """Программу переразмечают: это исправление, а не новый курс."""

        headers = await make_auth_headers()
        course = await _course(
            async_client, headers, title="Пожарно-технический минимум", discipline=None
        )
        patched = await async_client.patch(
            f"{_TRAINING_API}/courses/{course['id']}",
            json={"discipline": "fire_safety"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["discipline_label"] == "Пожарная безопасность"

    async def test_разметку_можно_снять(
        self, async_client, make_auth_headers
    ) -> None:
        """Ошиблись дисциплиной — снять её честнее, чем оставить ложную."""

        headers = await make_auth_headers()
        course = await _course(async_client, headers, title="Курс со снятием")
        patched = await async_client.patch(
            f"{_TRAINING_API}/courses/{course['id']}",
            json={"discipline": None},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["discipline"] is None

    async def test_фильтр_по_дисциплине_отдаёт_только_свои(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        await _course(async_client, headers, title="Курсовое обучение по ГО")
        await _course(
            async_client, headers, title="Обучение по отходам", discipline="ecology"
        )
        await _course(
            async_client, headers, title="Курс без разметки", discipline=None
        )

        listed = await async_client.get(
            f"{_TRAINING_API}/courses",
            params={"discipline": "civil_defense"},
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        titles = [row["title"] for row in listed.json()["items"]]
        assert titles == ["Курсовое обучение по ГО"]

    async def test_без_фильтра_видны_все_включая_неразмеченные(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        await _course(async_client, headers, title="Программа ГО")
        await _course(async_client, headers, title="Без разметки", discipline=None)
        listed = await async_client.get(f"{_TRAINING_API}/courses", headers=headers)
        titles = {row["title"] for row in listed.json()["items"]}
        assert {"Программа ГО", "Без разметки"} <= titles


class TestКонтурГОВидитСвоиПрограммы:
    async def test_сводка_го_считает_свои_программы(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker, "civil_defense")
        await _course(async_client, headers, title="Курсовое обучение по ГО")
        await _course(
            async_client, headers, title="Вводный инструктаж по ГО", discipline="civil_defense"
        )
        await _course(
            async_client, headers, title="Обучение по отходам", discipline="ecology"
        )

        readiness = await async_client.get(f"{_CD_API}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["training_programs"] == 2

    async def test_чужая_дисциплина_в_сводку_го_не_попадает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker, "civil_defense")
        await _course(
            async_client, headers, title="ПТМ", discipline="fire_safety"
        )
        await _course(async_client, headers, title="Неразмеченный", discipline=None)
        readiness = await async_client.get(f"{_CD_API}/readiness", headers=headers)
        assert readiness.json()["training_programs"] == 0

    async def test_контур_го_показывает_программы_но_не_владеет_ими(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Реестр остаётся в ядре: заводить курс через ручки ГО нельзя."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "civil_defense")
        await _course(async_client, headers, title="Курсовое обучение по ГО")

        listed = await async_client.get(
            f"{_CD_API}/training-programs", headers=headers
        )
        assert listed.status_code == 200, listed.text
        assert [row["title"] for row in listed.json()["items"]] == [
            "Курсовое обучение по ГО"
        ]
        # Заводить программу через контур ГО НЕЛЬЗЯ — это ядро.
        created = await async_client.post(
            f"{_CD_API}/training-programs",
            json={"title": "Через контур ГО"},
            headers=headers,
        )
        assert created.status_code == 405, created.text


class TestСловарьИГраница:
    def test_словарь_дисциплин_общий_а_не_копия(self) -> None:
        """Две копии словаря разъедутся при первой же новой дисциплине."""

        from app.schemas.training import TRAINING_DISCIPLINE_TITLES

        assert TRAINING_DISCIPLINE_TITLES is DISCIPLINE_TITLES

    def test_допустимые_значения_совпадают_с_перечислением(self) -> None:
        from app.schemas.training import TRAINING_DISCIPLINE_TITLES

        assert set(TRAINING_DISCIPLINE_TITLES) == set(Discipline)

    def test_фронт_знает_те_же_дисциплины(self) -> None:
        """Сторож против дрейфа: список на фронте написан руками.

        Тот же класс, что подписи видов комиссий и источники календаря: не
        обнови фронт — дисциплину нельзя будет ни выбрать, ни прочитать.
        """

        page = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "api"
            / "training.ts"
        )
        text = page.read_text(encoding="utf-8")
        block = re.search(
            r"TRAINING_DISCIPLINE_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся словарь дисциплин на фронте"
        front = set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))
        assert front == {d.value for d in Discipline}, sorted(
            front ^ {d.value for d in Discipline}
        )

    async def test_платформа_не_назначает_дисциплину_и_не_требует_программ(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: какие программы нужны — решают категория и орган."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "civil_defense")
        body = await _course(async_client, headers)
        forbidden = {
            "suggested_discipline",
            "required_programs",
            "programs_missing",
            "training_required",
        }
        assert forbidden.isdisjoint(body.keys())
        readiness = await async_client.get(f"{_CD_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())
