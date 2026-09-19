import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    IdempotencyKey,
    IdempotencyStatus,
    MedicalExam,
    Person,
    PipelineRun,
    PipelineRunStatus,
    PPEIssue,
    PPEIssueStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
    Training,
    TrainingStatus,
)
from app.schemas.task import TaskAcceptedResponse


@pytest.mark.anyio
async def test_document_generate_idempotency(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        template = Template(
            tenant_id=tenant.id,
            name="SAFETY_DOC",
            description="",
            metadata_json={},
            storage_key="templates/safety.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/safety.docx",
        )
        session.add(version)

        company = Company(tenant_id=tenant.id, name="ACME LLC")
        session.add(company)
        await session.flush()

        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Jane",
            last_name="Doe",
        )
        session.add(person)
        await session.commit()

        company_id = company.id
        person_id = person.id

    calls: list[tuple[tuple, dict]] = []

    def fake_apply_async(*args, **kwargs):
        calls.append((args, kwargs))

        class _Result:
            id = kwargs.get("task_id", str(uuid.uuid4()))

        return _Result()

    monkeypatch.setattr("app.tasks._core.generate_document_task.apply_async", fake_apply_async)

    headers = {**await make_auth_headers(), "Idempotency-Key": "doc-key-123"}
    payload = {
        "template_code": "SAFETY_DOC",
        "template_version": 1,
        "company_id": company_id,
        "person_id": person_id,
        "data": {"employee": "Jane"},
    }

    first = await async_client.post(
        "/api/v1/documents/generate",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 202, first.text
    second = await async_client.post(
        "/api/v1/documents/generate",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 202, second.text
    assert TaskAcceptedResponse.model_validate(
        second.json()
    ) == TaskAcceptedResponse.model_validate(first.json())
    assert len(calls) == 1

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(IdempotencyKey).where(IdempotencyKey.endpoint == "documents.generate")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        record = rows[0]
        assert record.status is IdempotencyStatus.SUCCEEDED
        assert record.result_json["body"]["task_id"] == first.json()["task_id"]

        runs = (await session.execute(select(PipelineRun))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status in {PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING}


@pytest.mark.anyio
async def test_pack_run_idempotency(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        company = Company(tenant_id=tenant.id, name="Widgets LLC")
        session.add(company)
        await session.flush()

        template = Template(
            tenant_id=tenant.id,
            name="ENTRY_FORM",
            description="",
            metadata_json={},
            storage_key="templates/entry.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/entry.docx",
        )
        session.add(version)

        pack = DocumentPack(
            tenant_id=tenant.id,
            code="ENTRY",
            name="Entry Pack",
            description="",
        )
        session.add(pack)
        await session.flush()

        item = DocumentPackItem(
            tenant_id=tenant.id,
            pack_id=pack.id,
            template_id=template.id,
            template_version_id=version.id,
            order=1,
            required=True,
        )
        session.add(item)

        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="John",
            last_name="Smith",
        )
        session.add(person)

        now = datetime.now(timezone.utc)
        await session.flush()
        session.add(
            Training(
                tenant_id=tenant.id,
                person_id=person.id,
                course_name="Safety",
                status=TrainingStatus.COMPLETED,
                completed_at=now + timedelta(days=30),
                expires_at=now + timedelta(days=30),
            )
        )
        session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=now.date(),
                valid_until=(now + timedelta(days=30)).date(),
            )
        )
        session.add(
            PPEIssue(
                tenant_id=tenant.id,
                person_id=person.id,
                item_name="Helmet",
                status=PPEIssueStatus.ISSUED,
                expires_at=now + timedelta(days=30),
            )
        )

        await session.commit()

        company_id = company.id
        pack_code = pack.code
        person_id = person.id

    task_calls: list[str] = []

    class StubResult:
        def __init__(self, run_id: str) -> None:
            self.id = f"queued-{run_id}"

    def fake_apply_async(
        *,
        args: list[str],
        kwargs: dict[str, str],
        task_id: str,
        headers: dict[str, str],
    ):
        run_id = args[0]
        task_calls.append(run_id)
        assert kwargs.get("tenant_slug")
        assert headers.get("trace_id")
        assert task_id == run_id
        return StubResult(run_id)

    monkeypatch.setattr("app.api.routes.packs.generate_document_task.apply_async", fake_apply_async)

    headers = {**await make_auth_headers(), "Idempotency-Key": "pack-key-123"}
    payload = {
        "pack_code": pack_code,
        "company_id": company_id,
        "person_ids": [person_id],
        "site_id": None,
        "context": {},
    }

    first = await async_client.post(
        "/api/v1/packs/run",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 202, first.text
    second = await async_client.post(
        "/api/v1/packs/run",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 202, second.text
    assert first.json() == second.json()
    assert len(task_calls) == 1

    async with sessionmaker() as session:
        records = (
            (
                await session.execute(
                    select(IdempotencyKey).where(IdempotencyKey.endpoint == "packs.run")
                )
            )
            .scalars()
            .all()
        )
        assert len(records) == 1
        assert records[0].status is IdempotencyStatus.SUCCEEDED
        body = records[0].result_json["body"]
        assert body["batch_id"] == first.json()["batch_id"]


@pytest.mark.anyio
async def test_documents_generate_requires_idempotency_key(
    async_client: AsyncClient,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/documents/generate",
        json={
            "template_code": "demo",
            "template_version": 1,
            "company_id": "company",
            "data": {},
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()
    assert payload["code"] == "BAD_REQUEST"
    assert payload["message"] == "Idempotency-Key header is required"


@pytest.mark.anyio
async def test_packs_run_requires_idempotency_key(
    async_client: AsyncClient,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": "ANY",
            "company_id": "company",
            "site_id": None,
            "person_ids": [],
            "data": {},
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()
    assert payload["code"] == "BAD_REQUEST"
    assert payload["message"] == "Idempotency-Key header is required"


# ---------------------------------------------------------------------------
# Explicit same-key/same-hash => replay contract
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_document_generate_replay_same_key_same_hash(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same Idempotency-Key + identical payload → 202 replay, task dispatched once."""
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        template = Template(
            tenant_id=tenant.id,
            name="REPLAY_SAME_HASH_DOC",
            description="",
            metadata_json={},
            storage_key="templates/replay_same_hash.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum_replay_same",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/replay_same_hash.docx",
        )
        session.add(version)

        company = Company(tenant_id=tenant.id, name="Replay Same Corp")
        session.add(company)
        await session.flush()

        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Replay",
            last_name="SameUser",
        )
        session.add(person)
        await session.commit()

        company_id = str(company.id)
        person_id = str(person.id)

    task_calls: list[object] = []

    def _fake_apply(*args: object, **kwargs: object) -> object:
        task_calls.append(kwargs)

        class _R:
            id = kwargs.get("task_id", str(uuid.uuid4()))

        return _R()

    monkeypatch.setattr("app.tasks._core.generate_document_task.apply_async", _fake_apply)

    headers = {**await make_auth_headers(), "Idempotency-Key": "replay-same-hash-key-001"}
    payload = {
        "template_code": "REPLAY_SAME_HASH_DOC",
        "template_version": 1,
        "company_id": company_id,
        "person_id": person_id,
        "data": {"employee": "ReplaySame"},
    }

    first = await async_client.post("/api/v1/documents/generate", json=payload, headers=headers)
    assert first.status_code == 202, first.text

    second = await async_client.post("/api/v1/documents/generate", json=payload, headers=headers)
    assert second.status_code == 202, second.text
    assert second.json() == first.json(), "replay must return the cached response body"
    assert len(task_calls) == 1, "Celery task must not be dispatched a second time on replay"


# ---------------------------------------------------------------------------
# Explicit same-key/different-hash => 409 contract
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_document_generate_conflict_same_key_different_hash(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same Idempotency-Key + different payload → 409 IDEMPOTENCY_MISMATCH."""
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        template = Template(
            tenant_id=tenant.id,
            name="CONFLICT_DIFF_HASH_DOC",
            description="",
            metadata_json={},
            storage_key="templates/conflict_diff_hash.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum_conflict_diff",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/conflict_diff_hash.docx",
        )
        session.add(version)

        company = Company(tenant_id=tenant.id, name="Conflict Diff Corp")
        session.add(company)
        await session.flush()

        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Conflict",
            last_name="DiffUser",
        )
        session.add(person)
        await session.commit()

        company_id = str(company.id)
        person_id = str(person.id)

    monkeypatch.setattr(
        "app.tasks._core.generate_document_task.apply_async",
        lambda *a, **kw: type("R", (), {"id": kw.get("task_id", "fake-id")})(),
    )

    headers = {**await make_auth_headers(), "Idempotency-Key": "conflict-diff-hash-key-002"}
    base = {
        "template_code": "CONFLICT_DIFF_HASH_DOC",
        "template_version": 1,
        "company_id": company_id,
        "person_id": person_id,
    }

    first = await async_client.post(
        "/api/v1/documents/generate",
        json={**base, "data": {"employee": "Alice"}},
        headers=headers,
    )
    assert first.status_code == 202, first.text

    second = await async_client.post(
        "/api/v1/documents/generate",
        json={**base, "data": {"employee": "Bob"}},
        headers=headers,
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body.get("code") == "IDEMPOTENCY_MISMATCH", f"unexpected code: {body}"
    assert body.get("type") == "idempotency", f"unexpected type: {body}"


@pytest.mark.anyio
async def test_packs_run_conflict_same_key_different_hash(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
) -> None:
    """Same Idempotency-Key + different payload → 409 IDEMPOTENCY_MISMATCH for packs/run.

    Uses a pre-seeded IdempotencyKey record so the test does not require full pack
    fixture setup.  The seeded request_hash is an arbitrary string that will never
    match the real SHA-256 fingerprint computed from the request body, which reliably
    triggers the conflict branch in IdempotencyService.acquire().
    """
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        seeded = IdempotencyKey(
            tenant_id=str(tenant.id),
            endpoint="packs.run",
            key="packs-conflict-diff-hash-003",
            status=IdempotencyStatus.SUCCEEDED,
            request_hash="seeded_fake_hash_that_never_matches_real_sha256_fingerprint",
            method="POST",
            path="/api/v1/packs/run",
            last_seen_at=datetime.now(tz=timezone.utc),
        )
        session.add(seeded)
        await session.commit()

    headers = {
        **await make_auth_headers(),
        "Idempotency-Key": "packs-conflict-diff-hash-003",
    }

    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": "ANY_CODE",
            "company_id": str(uuid.uuid4()),
            "site_id": None,
            "person_ids": [],
            "context": {},
        },
        headers=headers,
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body.get("code") == "IDEMPOTENCY_MISMATCH", f"unexpected code: {body}"
    assert body.get("type") == "idempotency", f"unexpected type: {body}"


@pytest.mark.anyio
async def test_уборка_удаляет_старые_записи_и_бережёт_свежие(test_db_session, data_factory) -> None:
    """Срез-231. Единственный путь удаления записей — эта уборка, и до среза её
    НИКТО НЕ ЗАПУСКАЛ: в расписании её не было, из кода не звали.

    Настройка срока хранения при этом существовала (``IDEMPOTENCY_TTL_DAYS``,
    по умолчанию 30 дней), то есть продукт обещал чистку и не делал её. Ключи
    копились вечно у каждого арендатора.

    Здесь проверяется сама работа: старую завершённую запись убирает, свежую и
    незавершённую оставляет. Ставить в расписание механизм, который не проверен,
    нельзя.
    """

    from app.services.idempotency import cleanup_idempotency_keys

    tenant = await data_factory.ensure_tenant(slug="idem-clean", session=test_db_session)
    now = datetime.now(tz=timezone.utc)

    stale = IdempotencyKey(
        tenant_id=str(tenant.id),
        endpoint="POST /documents:generate",
        key="stale-key",
        status=IdempotencyStatus.SUCCEEDED,
        updated_at=now - timedelta(days=45),
    )
    fresh = IdempotencyKey(
        tenant_id=str(tenant.id),
        endpoint="POST /documents:generate",
        key="fresh-key",
        status=IdempotencyStatus.SUCCEEDED,
        updated_at=now - timedelta(days=1),
    )
    # Незавершённую (`pending`) не трогаем даже старую: по ней ещё может прийти повтор.
    in_flight = IdempotencyKey(
        tenant_id=str(tenant.id),
        endpoint="POST /documents:generate",
        key="in-flight-key",
        status=IdempotencyStatus.PENDING,
        updated_at=now - timedelta(days=45),
    )
    test_db_session.add_all([stale, fresh, in_flight])
    await test_db_session.flush()

    removed = await cleanup_idempotency_keys(session=test_db_session, ttl_days=30)

    assert removed == 1, "убрать должна была ровно одну запись — старую завершённую"
    left = set(
        (
            await test_db_session.execute(
                select(IdempotencyKey.key).where(IdempotencyKey.tenant_id == str(tenant.id))
            )
        )
        .scalars()
        .all()
    )
    assert left == {"fresh-key", "in-flight-key"}
