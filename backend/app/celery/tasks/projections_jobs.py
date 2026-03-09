from __future__ import annotations

from app.services.celery_app import celery_app


@celery_app.task(name="app.rebuild_dashboard_snapshots_job")
def rebuild_dashboard_snapshots_job(*args, **kwargs):
    return {"status": "queued", "task": "rebuild_dashboard_snapshots_job"}


@celery_app.task(name="app.rebuild_package_projection_job")
def rebuild_package_projection_job(*args, **kwargs):
    return {"status": "queued", "task": "rebuild_package_projection_job"}


@celery_app.task(name="app.rebuild_person_compliance_projection_job")
def rebuild_person_compliance_projection_job(*args, **kwargs):
    return {"status": "queued", "task": "rebuild_person_compliance_projection_job"}


@celery_app.task(name="app.rebuild_site_safety_projection_job")
def rebuild_site_safety_projection_job(*args, **kwargs):
    return {"status": "queued", "task": "rebuild_site_safety_projection_job"}


@celery_app.task(name="app.rebuild_contractor_readiness_projection_job")
def rebuild_contractor_readiness_projection_job(*args, **kwargs):
    return {"status": "queued", "task": "rebuild_contractor_readiness_projection_job"}


@celery_app.task(name="app.reindex_search_entity_job")
def reindex_search_entity_job(*args, **kwargs):
    return {"status": "queued", "task": "reindex_search_entity_job"}


@celery_app.task(name="app.rebuild_client_portal_projection_job")
def rebuild_client_portal_projection_job(*args, **kwargs):
    return {"status": "queued", "task": "rebuild_client_portal_projection_job"}
