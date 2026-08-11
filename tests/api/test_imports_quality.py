"""OPS-71 срез-7 (разд. 71.3): проверки Data Quality по итогам импорта.

ТЗ: «Импортированные данные сразу проходят проверки Data Quality; проблемные —
помечаются, а не тихо принимаются».

Что закрепляется:

* итог проверки ложится в ту же партию — иначе «помечаются» негде увидеть;
* **в отчёт попадают только записи ЭТОЙ загрузки**: движок считает по всему
  арендатору, и без сужения человек увидел бы чужие давние проблемы вперемешку
  со своими — такой отчёт не чинит никто;
* **провал проверки не отменяет импорт**: данные уже записаны, и вспомогательная
  проверка не может превратить успешную операцию в 500;
* усечение примера видно (`sample_truncated`);
* проверка партии-предпросмотра отвергается: там ничего не записано.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from app.modules.data_quality.schemas import (
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    IssueType,
)
from app.modules.imports import quality as quality_module

API = "/api/v1/imports"
HEADER = "Организация,Фамилия,Имя,Табельный номер\n"


def _csv(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode("utf-8")


def _upload(content: bytes, name: str = "staff.csv") -> dict:
    return {"file": (name, content, "text/csv")}


@pytest.fixture()
async def imports_tenant(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        await session.commit()
        return tenant


def _issue(entity_id: str, severity: IssueSeverity = IssueSeverity.HIGH) -> DataQualityIssue:
    return DataQualityIssue(
        id=f"issue-{entity_id}",
        issue_type=IssueType.MISSING_FIELD,
        severity=severity,
        title="Не заполнена дата рождения",
        affected_entity_type="employee",
        affected_entity_id=entity_id,
        affected_entity_name="Иванов Иван",
    )


def _report(issues: list[DataQualityIssue]) -> DataQualityReport:
    return DataQualityReport(
        tenant_id="t",
        generated_at="2026-07-30T10:00:00Z",
        total_issues=len(issues),
        completeness_percent=90.0,
        issues=issues,
        issues_by_severity={},
        issues_by_type={},
        critical_issues=0,
        high_issues=len(issues),
        medium_issues=0,
        low_issues=0,
        check_results=[],
    )


def _patch_engine(monkeypatch: pytest.MonkeyPatch, issues_for) -> None:
    """Подменяем движок правил: срез проверяет СВЯЗКУ, а не сами правила."""

    async def _run(self):  # noqa: ANN001 - сигнатура метода сервиса
        return _report(issues_for())

    monkeypatch.setattr(
        quality_module.DataQualityService, "run_comprehensive_check", _run, raising=True
    )


async def _apply(async_client: AsyncClient, headers) -> dict:
    response = await async_client.post(
        f"{API}/persons/apply",
        files=_upload(_csv("АКМЕ,Иванов,Иван,001\n")),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["batch"]


async def _entity_id(async_client: AsyncClient, headers, batch_id: str) -> str:
    rows = (await async_client.get(f"{API}/batches/{batch_id}/rows", headers=headers)).json()
    created = [r for r in rows if r["action"] == "created" and r["entity_id"]]
    assert created, rows
    return created[0]["entity_id"]


@pytest.mark.anyio
class TestQualityCheck:
    async def test_issues_of_this_batch_land_in_the_batch(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, monkeypatch
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch = await _apply(async_client, headers)
        entity_id = await _entity_id(async_client, headers, batch["id"])
        _patch_engine(monkeypatch, lambda: [_issue(entity_id)])

        response = await async_client.post(
            f"{API}/batches/{batch['id']}/quality-check", headers=headers
        )

        assert response.status_code == 200, response.text
        quality = response.json()["notes"]["data_quality"]
        assert quality["issues_total"] == 1
        assert quality["by_severity"] == {"high": 1}
        assert quality["sample"][0]["entity_id"] == entity_id

    async def test_foreign_issues_are_filtered_out(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, monkeypatch
    ) -> None:
        """Чужие давние проблемы в отчёте о МОЕЙ загрузке никто не чинит."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch = await _apply(async_client, headers)
        entity_id = await _entity_id(async_client, headers, batch["id"])
        _patch_engine(
            monkeypatch, lambda: [_issue(entity_id), _issue("someone-else"), _issue("older-one")]
        )

        response = await async_client.post(
            f"{API}/batches/{batch['id']}/quality-check", headers=headers
        )

        quality = response.json()["notes"]["data_quality"]
        assert quality["issues_total"] == 1
        assert [s["entity_id"] for s in quality["sample"]] == [entity_id]

    async def test_sample_truncation_is_visible(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, monkeypatch
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch = await _apply(async_client, headers)
        entity_id = await _entity_id(async_client, headers, batch["id"])
        monkeypatch.setattr(quality_module, "MAX_QUALITY_SAMPLE", 2)
        _patch_engine(monkeypatch, lambda: [_issue(entity_id) for _ in range(5)])

        response = await async_client.post(
            f"{API}/batches/{batch['id']}/quality-check", headers=headers
        )

        quality = response.json()["notes"]["data_quality"]
        assert quality["issues_total"] == 5
        assert len(quality["sample"]) == 2
        assert quality["sample_truncated"] is True

    async def test_engine_failure_does_not_break_the_batch(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, monkeypatch
    ) -> None:
        """Данные уже записаны — вспомогательная проверка не может отдать 500."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch = await _apply(async_client, headers)
        await _entity_id(async_client, headers, batch["id"])

        async def _boom(self):  # noqa: ANN001
            raise RuntimeError("rule engine exploded")

        monkeypatch.setattr(
            quality_module.DataQualityService, "run_comprehensive_check", _boom, raising=True
        )

        response = await async_client.post(
            f"{API}/batches/{batch['id']}/quality-check", headers=headers
        )

        assert response.status_code == 200, response.text
        assert "rule engine exploded" in response.json()["notes"]["data_quality"]["error"]

    async def test_clean_import_reports_zero(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, monkeypatch
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch = await _apply(async_client, headers)
        _patch_engine(monkeypatch, list)

        response = await async_client.post(
            f"{API}/batches/{batch['id']}/quality-check", headers=headers
        )

        assert response.json()["notes"]["data_quality"]["issues_total"] == 0

    async def test_preview_batch_cannot_be_checked(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, monkeypatch
    ) -> None:
        import app.modules.imports.api as imports_api

        headers = await make_auth_headers(RoleEnum.ADMIN)
        monkeypatch.setattr(imports_api, "store_source", lambda **kw: None)
        monkeypatch.setattr(imports_api, "discard_source", lambda key: None)

        class _Task:
            @staticmethod
            def delay(*args):
                return None

        monkeypatch.setattr(imports_api, "run_import_batch_job", _Task)

        enqueued = await async_client.post(
            f"{API}/persons/dry-run-async",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001\n")),
            headers=headers,
        )
        batch_id = enqueued.json()["id"]

        response = await async_client.post(
            f"{API}/batches/{batch_id}/quality-check", headers=headers
        )

        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "IMPORT_BATCH_IS_PREVIEW"

    async def test_unknown_batch_is_404(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.post(
            f"{API}/batches/00000000-0000-0000-0000-000000000000/quality-check",
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 404
