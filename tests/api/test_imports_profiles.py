"""OPS-71 срез-8 (разд. 71.2): профили типовых источников (1С, Excel, конкуренты).

ТЗ: «Готовые сценарии переезда снижают барьер входа — это прямой инструмент
продаж». Профиль знает, как названы колонки в ЧУЖОМ файле и что с ними сделать.

Что закрепляется:

* **разбор «ФИО» одной колонкой** — без него профиль для 1С бесполезен:
  сопоставить одну колонку с тремя полями невозможно, и пользователю пришлось бы
  править файл руками, то есть делать ровно ту работу, которую профиль снимает;
* хвост длинного ФИО не теряется (двойные фамилии, отчество из двух слов);
* профиль опознаётся по заголовкам и предлагается ПОДСКАЗКОЙ, а применяется
  только по явной просьбе: он меняет трактовку колонок, ошибиться тут дороже;
* ручной выбор пользователя сильнее профиля — перед нами может быть вариация
  типового файла;
* профиль чужой цели отвергается, а не игнорируется молча.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.master_data import Person
from app.models.models import RoleEnum
from app.modules.imports.profiles import ZUP_PERSONS, apply_profile_splits, detect_profile

API = "/api/v1/imports"

# Заголовки как в типовой выгрузке 1С:ЗУП — ФИО одной ячейкой.
ZUP_HEADER = "Организация,ФИО,Табельный номер,Дата приема\n"


def _zup_csv(*rows: str) -> bytes:
    return (ZUP_HEADER + "".join(rows)).encode("utf-8")


def _upload(content: bytes, name: str = "zup.csv") -> dict:
    return {"file": (name, content, "text/csv")}


@pytest.fixture()
async def imports_tenant(sessionmaker, data_factory):
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "imports"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="imports", title="Импорт данных")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=True))
        await session.commit()
        return tenant


async def _count_persons(sessionmaker, tenant_id: str) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(Person)
                .where(Person.tenant_id == tenant_id, Person.deleted_at.is_(None))
            )
        ).scalar_one()


class TestSplitPureDomain:
    def test_fio_splits_into_three_fields(self) -> None:
        rows: list[dict[str, object]] = [{"ФИО": "Иванов Иван Сергеевич"}]

        added = apply_profile_splits(ZUP_PERSONS, rows)

        assert set(added) == {"last_name", "first_name", "middle_name"}
        assert rows[0]["last_name"] == "Иванов"
        assert rows[0]["first_name"] == "Иван"
        assert rows[0]["middle_name"] == "Сергеевич"

    def test_long_tail_is_not_lost(self) -> None:
        """Отчество из двух слов не должно обрезаться."""

        rows: list[dict[str, object]] = [{"ФИО": "Иванов Иван Сергеевич Оглы"}]

        apply_profile_splits(ZUP_PERSONS, rows)

        assert rows[0]["middle_name"] == "Сергеевич Оглы"

    def test_two_word_name_leaves_middle_empty(self) -> None:
        rows: list[dict[str, object]] = [{"ФИО": "Иванов Иван"}]

        apply_profile_splits(ZUP_PERSONS, rows)

        assert rows[0]["last_name"] == "Иванов"
        assert rows[0]["first_name"] == "Иван"
        assert "middle_name" not in rows[0]

    def test_detection_requires_every_signature_column(self) -> None:
        assert detect_profile("persons", ["Организация", "ФИО", "Табельный номер"]) is ZUP_PERSONS
        # Без табельного номера это уже не выгрузка ЗУП, а обычная таблица с ФИО.
        assert detect_profile("persons", ["Организация", "ФИО"]).code == "excel_persons_fio"
        assert detect_profile("persons", ["Фамилия", "Имя"]) is None


@pytest.mark.anyio
class TestProfilesApi:
    async def test_profiles_are_listed_and_filtered_by_target(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get(f"{API}/profiles?target=persons", headers=headers)

        assert response.status_code == 200, response.text
        codes = {p["code"] for p in response.json()}
        assert "1c_zup_persons" in codes
        assert "excel_staff_list" not in codes  # это профиль должностей

    async def test_profile_is_only_suggested_until_asked_for(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        """Профиль меняет трактовку колонок — применять его без просьбы нельзя."""

        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(_zup_csv("АКМЕ,Иванов Иван Сергеевич,001,01.02.2020\n")),
            headers=headers,
        )

        assert response.status_code == 422, response.text
        # Без профиля колонки «Фамилия»/«Имя» в файле нет — файл отвергнут целиком.
        assert response.json()["detail"]["code"] == "IMPORT_REQUIRED_COLUMNS_MISSING"

    async def test_profile_makes_the_zup_export_importable(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)

        preview = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(_zup_csv("АКМЕ,Иванов Иван Сергеевич,001,01.02.2020\n")),
            data={"profile": "1c_zup_persons"},
            headers=headers,
        )

        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["counts"]["create"] == 1
        assert body["applied_profile"] == "1c_zup_persons"
        assert body["detected_profile"] == "1c_zup_persons"

        applied = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_zup_csv("АКМЕ,Иванов Иван Сергеевич,001,01.02.2020\n")),
            data={"profile": "1c_zup_persons"},
            headers=headers,
        )
        assert applied.status_code == 201, applied.text
        assert applied.json()["batch"]["created_count"] == 1
        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 1

    async def test_detection_is_reported_even_without_a_profile(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        """Подсказка полезна именно тогда, когда профиль не выбрали."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = "Организация,ФИО,Табельный номер,Фамилия,Имя\nАКМЕ,Иванов Иван,001,Иванов,Иван\n"

        response = await async_client.post(
            f"{API}/persons/dry-run", files=_upload(body.encode("utf-8")), headers=headers
        )

        assert response.status_code == 200, response.text
        assert response.json()["detected_profile"] == "1c_zup_persons"
        assert response.json()["applied_profile"] is None

    async def test_manual_mapping_wins_over_the_profile(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        """Перед нами может быть вариация типового файла."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = "Организация,ФИО,Табельный номер,Личный номер\nАКМЕ,Иванов Иван Сергеевич,001,Л-9\n"

        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(body.encode("utf-8")),
            data={
                "profile": "1c_zup_persons",
                "mapping": '{"personnel_number": "Личный номер"}',
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["mapping"]["personnel_number"] == "Личный номер"

    async def test_profile_of_another_target_is_refused(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(_zup_csv("АКМЕ,Иванов Иван,001,\n")),
            data={"profile": "excel_staff_list"},
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "IMPORT_PROFILE_TARGET_MISMATCH"

    async def test_unknown_profile_is_404(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(_zup_csv("АКМЕ,Иванов Иван,001,\n")),
            data={"profile": "no_such_profile"},
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 404, response.text
        assert response.json()["detail"]["code"] == "IMPORT_PROFILE_UNKNOWN"
