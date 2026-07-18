from __future__ import annotations

import asyncio

from app.celery.tasks import projections_jobs


def test_rebuild_package_projection_job_delegates(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(tenant_id, runner):
        captured["tenant_id"] = tenant_id
        captured["runner_name"] = runner.__code__.co_names
        return {"status": "ok", "tenant_id": tenant_id, "rebuilt": 3}

    monkeypatch.setattr(projections_jobs, "_run_projection_job", fake_run)

    result = projections_jobs.rebuild_package_projection_job(tenant_id="tenant-a")

    assert result["status"] == "ok"
    assert captured["tenant_id"] == "tenant-a"
    assert "rebuild_package_projection" in captured["runner_name"]


def test_rebuild_dashboard_snapshots_job_parses_snapshot_date(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(tenant_id, runner):
        captured["tenant_id"] = tenant_id

        class Dummy:
            async def rebuild_dashboard_snapshot(self, snapshot_date):
                captured["snapshot_date"] = snapshot_date.isoformat()
                return {"snapshot_date": snapshot_date.isoformat()}

        return {"status": "ok", "payload": asyncio.run(runner(Dummy()))}

    monkeypatch.setattr(projections_jobs, "_run_projection_job", fake_run)

    result = projections_jobs.rebuild_dashboard_snapshots_job(
        tenant_id="tenant-z", snapshot_date="2026-05-03"
    )

    assert result["status"] == "ok"
    assert captured["tenant_id"] == "tenant-z"
    assert captured["snapshot_date"] == "2026-05-03"
