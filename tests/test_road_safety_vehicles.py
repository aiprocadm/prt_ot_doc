"""Контур БДД срез-1 (Доп. №1 разд. 56.2): реестр транспортных средств.

Требование: «Транспортные средства: реестр ТС, техосмотр, страхование,
тахографы, лицензии/разрешения». Водители, путевые листы, предрейсовые осмотры
и учёт ДТП — следующие срезы: все они ссылаются на ТС, которого до сих пор не
существовало.

СВЕРКА нашла два расхождения:

1. **Контур БДД пуст полностью.** ТЗ отсылает к «transport safety (vNext
   §17.3)», но в коде нет ни одной модели транспорта: ни ТС, ни водителей, ни
   путевых листов. Есть только словарная строка дисциплины, комплект
   документов BDD_BASE и запись в библиотеке правил.
2. **Причина в библиотеке правил для ГО и ЧС ПРОТУХЛА — и сторож это
   пропустил.** Текст утверждает «в системе нет ни одного события ГО и ЧС: ни
   формирований, ни учений, ни планов», хотя формирования, учения и планы
   заведены срезами 56.1. Сторож, поставленный в срезе экологии, требовал лишь
   упоминания СОБЫТИЙ — и пропустил перечисление сущностей, которое
   протухает при первом же новом реестре. Здесь он усилен: причина не имеет
   права заявлять «нет ни одного», потому что это проверяемый факт, который
   ложен через один срез.

Решения:

* **гос. номер уникален у арендатора**: одна машина — одна запись; второй
  «А123АА777» это не второе ТС, а ошибка ввода;
* **пустой срок = «сведения не внесены», а НЕ «бессрочно»** — и это ОТЛИЧИЕ
  от документов ПБ и ГО, где пустой срок означал бессрочность. У диагностической
  карты и полиса ОСАГО бессрочности НЕ БЫВАЕТ: пустая дата значит только, что
  сведений нет. При этом «не внесено» и «просрочено» — тоже разные вещи;
* **просрочки считаются ТОЛЬКО по ТС в эксплуатации**: у списанной машины
  просроченный полис не проблема, и объявлять его нарушением — шум;
* **тахограф: «не установлен» — отдельное состояние**, а не пустой срок:
  отсутствие прибора и отсутствие сведений о поверке — разные факты.

ГРАНИЦА: платформа НЕ решает, нужен ли тахограф, требуется ли лицензия и какой
срок у диагностической карты. Это следует из вида перевозок, массы и категории
ТС по закону — таких данных в системе нет. Полей «требуется тахограф»,
«нужна лицензия» и «соответствует ли ТС» нет ни в записи, ни в сводке.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/road-safety"


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


async def _vehicle(
    async_client,
    headers,
    *,
    plate: str = "А123АА777",
    kind: str = "truck",
    status: str = "in_service",
    inspection_due: date | None = None,
    insurance_due: date | None = None,
    tachograph: bool = False,
    tachograph_due: date | None = None,
) -> dict:
    payload: dict[str, object] = {
        "plate_number": plate,
        "brand_model": "КамАЗ 5490",
        "kind": kind,
        "status": status,
        "tachograph_installed": tachograph,
    }
    if inspection_due is not None:
        payload["inspection_due"] = str(inspection_due)
    if insurance_due is not None:
        payload["insurance_due"] = str(insurance_due)
    if tachograph_due is not None:
        payload["tachograph_due"] = str(tachograph_due)
    response = await async_client.post(
        f"{_API}/vehicles", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestРеестрТС:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/vehicles", headers=headers)
        assert response.status_code == 404

    async def test_тс_заводится_с_видом_и_состоянием_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(
            async_client,
            headers,
            inspection_due=date.today() + timedelta(days=200),
            insurance_due=date.today() + timedelta(days=100),
        )
        assert body["kind_label"] == "Грузовой автомобиль"
        assert body["status_label"] == "В эксплуатации"
        assert body["inspection_status"] == "ok"
        assert body["insurance_status"] == "ok"

    async def test_неизвестный_вид_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/vehicles",
            json={"plate_number": "В001ВВ77", "brand_model": "X", "kind": "самолёт"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_неизвестное_состояние_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/vehicles",
            json={
                "plate_number": "В002ВВ77",
                "brand_model": "X",
                "kind": "truck",
                "status": "в ремонте навсегда",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_дубль_госномера_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Одна машина — одна запись: второй «А123АА777» это ошибка ввода."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="О777ОО77")
        response = await async_client.post(
            f"{_API}/vehicles",
            json={"plate_number": "О777ОО77", "brand_model": "Другая", "kind": "bus"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_списание_меняет_состояние_а_не_удаляет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Списанное ТС остаётся в истории парка."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers, plate="У555УУ77")
        patched = await async_client.patch(
            f"{_API}/vehicles/{vehicle['id']}",
            json={"status": "decommissioned"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status_label"] == "Списано"
        listed = await async_client.get(f"{_API}/vehicles", headers=headers)
        assert len(listed.json()["items"]) == 1


class TestСрокиДокументов:
    async def test_пустой_срок_это_не_внесено_а_не_бессрочно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ОТЛИЧИЕ от документов ПБ и ГО: у полиса бессрочности не бывает."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(async_client, headers, plate="Е111ЕЕ77")
        assert body["inspection_status"] == "missing"
        assert body["inspection_status_label"] == "Сведения не внесены"
        assert body["insurance_status"] == "missing"

    async def test_не_внесено_и_просрочено_это_разные_состояния(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(
            async_client,
            headers,
            plate="Е222ЕЕ77",
            insurance_due=date.today() - timedelta(days=3),
        )
        assert body["insurance_status"] == "overdue"
        assert body["insurance_status_label"] == "Просрочено"
        # А техосмотр не внесён — и это НЕ просрочка.
        assert body["inspection_status"] == "missing"

    async def test_близкий_срок_назван_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(
            async_client,
            headers,
            plate="Е333ЕЕ77",
            inspection_due=date.today() + timedelta(days=10),
        )
        assert body["inspection_status"] == "due_soon"
        assert body["inspection_status_label"] == "Скоро истекает"


class TestТахограф:
    async def test_не_установлен_это_отдельное_состояние(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Нет прибора и нет сведений о поверке — разные факты."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(async_client, headers, plate="Т100ТТ77", tachograph=False)
        assert body["tachograph_status"] == "not_installed"
        assert body["tachograph_status_label"] == "Не установлен"

    async def test_установлен_без_срока_поверки_это_не_внесено(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(async_client, headers, plate="Т200ТТ77", tachograph=True)
        assert body["tachograph_status"] == "missing"

    async def test_просроченная_поверка_названа_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(
            async_client,
            headers,
            plate="Т300ТТ77",
            tachograph=True,
            tachograph_due=date.today() - timedelta(days=1),
        )
        assert body["tachograph_status"] == "overdue"


class TestСводкаИГраница:
    async def test_просрочки_считаются_только_по_эксплуатируемым(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """У списанной машины просроченный полис — не проблема, а шум."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(
            async_client,
            headers,
            plate="Н001НН77",
            insurance_due=date.today() - timedelta(days=5),
        )
        decommissioned = await _vehicle(
            async_client,
            headers,
            plate="Н002НН77",
            insurance_due=date.today() - timedelta(days=500),
        )
        await async_client.patch(
            f"{_API}/vehicles/{decommissioned['id']}",
            json={"status": "decommissioned"},
            headers=headers,
        )

        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        body = readiness.json()
        assert body["total_vehicles"] == 2
        assert body["by_status"]["in_service"] == 1
        assert body["by_status"]["decommissioned"] == 1
        # Просрочка только у эксплуатируемой.
        assert body["insurance_overdue"] == 1

    async def test_сводка_считает_ТС_без_внесённых_сведений(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="Р001РР77")
        await _vehicle(
            async_client,
            headers,
            plate="Р002РР77",
            inspection_due=date.today() + timedelta(days=100),
            insurance_due=date.today() + timedelta(days=100),
        )
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.json()["documents_missing"] == 1

    async def test_платформа_не_решает_нужен_ли_тахограф_и_лицензия(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: это следует из вида перевозок, массы и категории ТС."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _vehicle(async_client, headers, plate="Г001ГГ77")
        forbidden = {
            "tachograph_required",
            "license_required",
            "compliant",
            "required_inspection_period_months",
        }
        assert forbidden.isdisjoint(body.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())

    async def test_чужое_тс_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/vehicles/00000000-0000-0000-0000-000000000000",
            json={"status": "suspended"},
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestПричиныВБиблиотекеПравил:
    """Починка собственного дрейфа, найденная сверкой этого среза.

    Причина для ГО и ЧС утверждала «нет ни одного события ГО и ЧС: ни
    формирований, ни учений, ни планов» — а формирования, учения и планы
    заведены пятью срезами 56.1. Сторож, поставленный срезом экологии, требовал
    лишь упоминания СОБЫТИЙ и перечисление сущностей пропускал.
    """

    def test_причина_не_заявляет_отсутствие_сущностей(self) -> None:
        """«Нет ни одного» — проверяемый факт, который протухает за один срез.

        Причина обязана говорить о том, что контур НЕ ИСПУСКАЕТ СОБЫТИЙ: это
        свойство кода, а не перечень таблиц, и оно не устаревает от появления
        нового реестра.
        """

        from app.domains.rules_library.library import DISCIPLINES_WITHOUT_RULES

        for discipline, reason in DISCIPLINES_WITHOUT_RULES.items():
            lowered = reason.lower()
            assert "нет ни одного" not in lowered, discipline.value
            assert "ни одного события" not in lowered, discipline.value

    def test_причина_по_прежнему_говорит_о_событиях(self) -> None:
        from app.domains.rules_library.library import DISCIPLINES_WITHOUT_RULES

        for discipline, reason in DISCIPLINES_WITHOUT_RULES.items():
            assert "событ" in reason.lower(), discipline.value
