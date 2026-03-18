from datetime import date, datetime, timezone
from app.models.models import Incident, IncidentSeverity, IncidentStatus, IncidentType, NPABinding, NPA, NPAStatus
from app.models.npa import NpaAct, NpaRevision
from app.models.notifications import Notification, NotificationChannel, NotificationPriority, NotificationStatus, NotificationType


async def test_workflow_definition_publish_start_and_complete(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(tenant=tenant, email="wf@example.com", session=session)
        await session.commit()
    headers = await make_auth_headers(email="wf@example.com")

    payload = {
        "code": "doc-approval",
        "name": "Document approval",
        "entity_type": "document",
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "name": "Start"},
                {"id": "approve", "type": "approval", "name": "Approve", "assignee_user_id": user.id},
                {"id": "notify", "type": "notification", "name": "Notify"},
                {"id": "end", "type": "end", "name": "End"},
            ],
            "transitions": [
                {"from": "start", "to": "approve"},
                {"from": "approve", "to": "notify"},
                {"from": "notify", "to": "end"},
            ],
        },
        "variables_schema": {"approved": "boolean"},
    }
    create_response = await async_client.post("/api/v1/workflow/definitions", json=payload, headers=headers)
    assert create_response.status_code == 201, create_response.text
    version_id = create_response.json()["id"]

    publish_response = await async_client.post(f"/api/v1/workflow/versions/{version_id}/publish", headers=headers)
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "published"

    second_create = await async_client.post("/api/v1/workflow/definitions", json=payload, headers=headers)
    assert second_create.status_code == 201
    second_version_id = second_create.json()["id"]
    second_publish = await async_client.post(f"/api/v1/workflow/versions/{second_version_id}/publish", headers=headers)
    assert second_publish.status_code == 200

    definitions_response = await async_client.get("/api/v1/workflow/definitions", headers=headers)
    versions = definitions_response.json()[0]["versions"]
    first_version = next(item for item in versions if item["id"] == version_id)
    assert first_version["status"] == "archived"

    start_response = await async_client.post(
        "/api/v1/workflow/instances",
        json={"definition_code": "doc-approval", "entity_type": "document", "entity_id": "doc-1", "context": {"approved": True}},
        headers=headers,
    )
    assert start_response.status_code == 201, start_response.text
    instance_payload = start_response.json()
    assert instance_payload["status"] == "waiting"
    assert len(instance_payload["tasks"]) == 1

    task_id = instance_payload["tasks"][0]["id"]
    complete_response = await async_client.post(
        f"/api/v1/workflow/tasks/{task_id}/complete",
        json={"decision": "approve", "payload": {"approved": True}},
        headers=headers,
    )
    assert complete_response.status_code == 200

    state_response = await async_client.get(f"/api/v1/workflow/instances/{instance_payload['id']}", headers=headers)
    assert state_response.status_code == 200
    state = state_response.json()
    assert state["status"] == "completed"
    assert any(item["event_type"] == "human_task_completed" for item in state["timeline"])
    assert any(item["event_type"] == "notification_queued" for item in state["timeline"])


async def test_notifications_filters_and_mark_all(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(tenant=tenant, email="notif@example.com", session=session)
        session.add_all([
            Notification(
                tenant_id=tenant.id,
                user_id=user.id,
                channel=NotificationChannel.INAPP,
                type=NotificationType.APPROVAL_DEADLINE,
                title="Approval due",
                body="Please approve",
                priority=NotificationPriority.CRITICAL,
                status=NotificationStatus.QUEUED,
                dedup_key="n1",
                scheduled_at=datetime.now(tz=timezone.utc),
            ),
            Notification(
                tenant_id=tenant.id,
                user_id=user.id,
                channel=NotificationChannel.EMAIL,
                type=NotificationType.INTEGRATION_ERROR,
                title="Integration failed",
                body="External sync failed",
                priority=NotificationPriority.HIGH,
                status=NotificationStatus.SENT,
                dedup_key="n2",
                scheduled_at=datetime.now(tz=timezone.utc),
            ),
        ])
        await session.commit()
    headers = await make_auth_headers(email="notif@example.com")

    response = await async_client.get("/api/v1/notifications", headers=headers, params={"priority": "critical", "channel": "inapp"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["priority"] == "critical"

    mark_response = await async_client.post("/api/v1/notifications/mark-read", headers=headers, json={"ids": []})
    assert mark_response.status_code == 200
    assert mark_response.json()["updated"] >= 1


async def test_npa_impact_detail_and_task_creation(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(tenant=tenant, email="npa@example.com", session=session)
        act = NpaAct(code="123-FZ", title="NPA Act", edition="v1")
        session.add(act)
        await session.flush()
        revision = NpaRevision(act_id=act.id, revision_code="rev-1", title="Revision 1", effective_from=date(2026, 1, 1))
        session.add(revision)
        session.add(NPABinding(tenant_id=tenant.id, npa_id=act.id, entity_type="template_version", entity_id="tpl-1", context={"risk_id": "risk-1", "workflow_definition_id": "wf-1", "site_id": "site-1"}))
        await session.commit()
    headers = await make_auth_headers(email="npa@example.com")

    detail = await async_client.get(f"/api/v1/npa/{act.id}", headers=headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["summary"]["templates"] == 1
    assert payload["summary"]["workflows"] == 1
    assert payload["revisions"][0]["revision_code"] == "rev-1"

    create_tasks = await async_client.post(f"/api/v1/npa/{act.id}/impact/tasks", headers=headers)
    assert create_tasks.status_code == 200
    assert create_tasks.json()["created"] >= 1


async def test_search_types_alias(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(tenant=tenant, email="search@example.com", session=session)
        npa = NPA(tenant_id=tenant.id, code="NPA-1", title="Safety rule", edition_date=date(2026, 1, 1), status=NPAStatus.ACTIVE)
        await session.merge(npa)
        await session.commit()
    headers = await make_auth_headers(email="search@example.com")

    response = await async_client.get("/api/v1/search", headers=headers, params={"q": "", "types": "document"})
    assert response.status_code == 200
    assert "facets" in response.json()


async def test_search_recent_and_saved_queries(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_user(tenant=tenant, email="search-history@example.com", session=session)
        await session.commit()
    headers = await make_auth_headers(email="search-history@example.com")

    response = await async_client.get("/api/v1/search", headers=headers, params={"q": "workflow", "types": "document"})
    assert response.status_code == 200

    recent = await async_client.get("/api/v1/search/recent", headers=headers)
    assert recent.status_code == 200
    assert recent.json()["items"][0]["q"] == "workflow"

    saved = await async_client.post("/api/v1/search/saved", headers=headers, json={"name": "WF docs", "q": "workflow", "types": ["document"], "filters": {"status": "active"}})
    assert saved.status_code == 201
    saved_id = saved.json()["id"]

    saved_list = await async_client.get("/api/v1/search/saved", headers=headers)
    assert saved_list.status_code == 200
    assert any(item["id"] == saved_id for item in saved_list.json()["items"])

    deleted = await async_client.delete(f"/api/v1/search/saved/{saved_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


async def test_workflow_task_cannot_be_completed_by_other_user(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        assignee = await data_factory.create_user(tenant=tenant, email="wf-owner@example.com", session=session)
        other_user = await data_factory.create_user(tenant=tenant, email="wf-other@example.com", session=session)
        await session.commit()
    owner_headers = await make_auth_headers(email="wf-owner@example.com")
    other_headers = await make_auth_headers(email="wf-other@example.com")

    payload = {
        "code": "restricted-doc-approval",
        "name": "Restricted approval",
        "entity_type": "document",
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "name": "Start"},
                {"id": "approve", "type": "approval", "name": "Approve", "assignee_user_id": assignee.id},
                {"id": "end", "type": "end", "name": "End"},
            ],
            "transitions": [
                {"from": "start", "to": "approve"},
                {"from": "approve", "to": "end"},
            ],
        },
        "variables_schema": {},
    }
    create_response = await async_client.post("/api/v1/workflow/definitions", json=payload, headers=owner_headers)
    version_id = create_response.json()["id"]
    await async_client.post(f"/api/v1/workflow/versions/{version_id}/publish", headers=owner_headers)
    start_response = await async_client.post(
        "/api/v1/workflow/instances",
        json={"definition_code": "restricted-doc-approval", "entity_type": "document", "entity_id": "doc-2", "context": {}},
        headers=owner_headers,
    )
    task_id = start_response.json()["tasks"][0]["id"]

    forbidden = await async_client.post(
        f"/api/v1/workflow/tasks/{task_id}/complete",
        json={"decision": "approve", "payload": {}},
        headers=other_headers,
    )
    assert forbidden.status_code == 403


async def test_search_indexes_multiple_registry_types(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_user(tenant=tenant, email="search-multi@example.com", session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="Acme Safety")
        site = await data_factory.create_site(tenant=tenant, session=session, company=company, name="Plant 7")
        incident = Incident(
            tenant_id=tenant.id,
            company_id=company.id,
            site_id=site.id,
            title="Forklift near miss",
            incident_type=IncidentType.NEAR_MISS,
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.REPORTED,
        )
        session.add(incident)
        await session.flush()
        await session.commit()

        from app.modules.projections.services import ProjectionOrchestrator

        await ProjectionOrchestrator(session, str(tenant.id)).rebuild_search_index()
        await session.commit()
    headers = await make_auth_headers(email="search-multi@example.com")

    response = await async_client.get("/api/v1/search", headers=headers, params={"q": "Forklift", "types": "incidents,sites,company"})
    assert response.status_code == 200
    payload = response.json()
    assert any(item["entity_type"] == "incident" and item["entity_id"] == incident.id for item in payload["items"])
    assert payload["facets"]["type_counts"]["incident"] >= 1
