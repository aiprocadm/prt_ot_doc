"""Журналы, которых не было: таймлайн прогона пакета и журнал задания (срез-133).

ЗАЧЕМ. Опись среза-131 нашла таблицы, которые кто-то читает, а не пишет никто.
Две из них — журналы, и у обеих есть экран:

* ``GET /packs/pack-runs/{id}/timeline`` читает ``pack_run_logs`` — таймлайн
  прогона был пуст всегда;
* ``GET /jobs/{id}`` читает ``job_logs`` — журнал задания был пуст всегда,
  хотя события шагов писались... в объектное хранилище отдельными файлами.
  То есть журнал существовал, но не там, куда смотрит экран.

Пустой журнал не выглядит поломкой: «событий не было» — обычное состояние для
только что созданной сущности. Поэтому заметить это можно было только зная,
что строк там не бывает в принципе.

ЧТО ПРОВЕРЯЕТСЯ: после настоящей работы (прогон пакета, шаг задания) в
журналах есть строки, и в них написано то, что произошло.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def _make_pack_run(async_client: AsyncClient, headers: dict[str, str], selected: list[int]):
    """Прогон пакета через настоящие ручки — как это делает человек."""

    profile = await async_client.post(
        "/api/v1/package-profiles",
        json={
            "code": f"pp-{uuid.uuid4().hex[:8]}",
            "name": "Профиль-133",
            "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
            "status": "active",
        },
        headers=headers,
    )
    assert profile.status_code == 201, profile.text
    preset = await async_client.post(
        "/api/v1/package-presets",
        json={
            "code": f"preset-{uuid.uuid4().hex[:8]}",
            "name": "Набор-133",
            "package_profile_id": profile.json()["id"],
            "naming_rule": "<doc>",
            "source_type": "json",
            "mapping_json": {"doc": {"type": "literal", "value": "документ"}},
            "status": "active",
        },
        headers=headers,
    )
    assert preset.status_code == 201, preset.text
    run = await async_client.post(
        "/api/v1/pack-runs",
        json={
            "package_preset_id": preset.json()["id"],
            "rows": [{"fio": "Иванов"}, {"fio": "Петров"}],
            "selected_rows": selected,
        },
        headers={**headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
    )
    assert run.status_code == 202, run.text
    return run.json()["pack_run_id"]


async def test_таймлайн_прогона_пакета_больше_не_пуст(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Экран времени показывал пустоту при любой работе."""

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    run_id = await _make_pack_run(async_client, headers, selected=[1, 2])

    response = await async_client.get(f"/api/v1/pack-runs/{run_id}/timeline", headers=headers)

    assert response.status_code == 200, response.text
    steps = [row["step"] for row in response.json()]
    assert steps == ["run_started", "run_finished"], response.json()
    started = response.json()[0]
    assert started["payload"]["selected_rows"] == 2
    assert "2" in started["message"]


async def test_отброшенные_строки_названы_вслух(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Молча уменьшенный отбор читается как «столько и просили».

    Строки вне диапазона источника отбрасываются давно (иначе итог считал бы
    больше документов, чем создано), но узнать об этом было неоткуда.
    """

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    run_id = await _make_pack_run(async_client, headers, selected=[1, 2, 7, 9])

    response = await async_client.get(f"/api/v1/pack-runs/{run_id}/timeline", headers=headers)

    assert response.status_code == 200, response.text
    dropped = [row for row in response.json() if row["step"] == "rows_dropped"]
    assert len(dropped) == 1, response.json()
    assert dropped[0]["level"] == "warning"
    assert dropped[0]["payload"]["dropped_rows"] == 2


async def test_журнал_задания_видит_события_шага(sessionmaker, data_factory) -> None:
    """События шага писались только файлом в хранилище — экран их не видел."""

    from sqlalchemy import select

    from app.models.job_engine import DocumentJobLog, DocumentJobStep
    from app.modules.pipelines.models import PipelineProfile
    from app.services.pipelines_orchestrator import PipelineOrchestrator

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            PipelineProfile(
                tenant_id=str(tenant.id),
                code="journal_v1",
                name="Журнал-133",
                steps=[{"code": "render_docx"}],
                limits={},
                is_active=True,
            )
        )
        await session.commit()
        tenant_id = str(tenant.id)

    async with sessionmaker() as session:
        orchestrator = PipelineOrchestrator(session)
        job = await orchestrator.create_job(
            tenant_id=tenant_id,
            profile_code="journal_v1",
            payload={"data": {"fio": "Иванов"}},
            idempotency_key=None,
            request_hash="hash-133",
            enqueue=False,
        )
        await session.commit()
        job_id = job.id

    async with sessionmaker() as session:
        step_id = (
            (
                await session.execute(
                    select(DocumentJobStep.id).where(DocumentJobStep.job_id == job_id)
                )
            )
            .scalars()
            .first()
        )
        orchestrator = PipelineOrchestrator(session)
        await orchestrator.run_step(job_id=job_id, step_id=step_id)
        await session.commit()

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(DocumentJobLog)
                    .where(DocumentJobLog.job_id == job_id)
                    .order_by(DocumentJobLog.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    assert rows, "журнал задания пуст — событий шага в нём снова нет"
    assert rows[0].message == "step_started"
    assert rows[0].step_code
