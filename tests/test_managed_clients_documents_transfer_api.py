"""BIZ-49 срез-19 — документы клиента и их файлы (разд. 49.1).

Последний класс данных, который оставался у аутсорсера. Он ждал решения
владельца: у документа ``created_by`` NOT NULL с RESTRICT, то есть копию надо
на кого-то записать. Решение (2026-08-08): авторство — владелец клиента.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.document import Document, DocumentStatus
from app.models.file import File, FileKind, FileScanStatus
from app.models.identity import User
from app.models.managed_clients import ManagedClient
from app.models.master_data import Company, Person
from app.models.models import Tenant
from app.models.templates import Template, TemplateStatus
from app.models.tenant_billing import RoleEnum
from app.services.file_storage import FileStorageService

_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


def _auth(sub="admin-1"):
    return SimpleNamespace(sub=sub, tenant_id=_TENANT, roles=["admin"], company_id=None)


def _request():
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


class _TrustedWrapper:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._orig_commit = self._session.commit
        self._session.commit = self._session.flush
        return self._session

    async def __aexit__(self, *exc):
        self._session.commit = self._orig_commit
        return False


async def _setup(session, *, with_owner=True):
    company = Company(tenant_id=_TENANT, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    person = Person(tenant_id=_TENANT, company_id=company.id, first_name="Иван", last_name="Иванов")
    session.add(person)
    target = Tenant(
        slug="romashka",
        code="romashka",
        name="Ромашка",
        schema_name="tenant_romashka",
        contact_email="r@r.ru",
    )
    session.add(target)
    await session.flush()
    if with_owner:
        session.add(
            User(
                tenant_id=target.id,
                email="owner@romashka.ru",
                full_name="Tenant Owner",
                role=RoleEnum.OWNER,
                hashed_password="x",
                is_active=True,
            )
        )
    client = ManagedClient(
        tenant_id=_TENANT,
        name="ООО Ромашка",
        mode=ManagedClientMode.DEDICATED,
        company_id=company.id,
        dedicated_tenant_slug="romashka",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(client)
    await session.flush()
    return SimpleNamespace(client=client, company=company, person=person, target=target)


async def _template(session, *, code="INSTR-1", name="Инструкция по ОТ"):
    row = Template(
        tenant_id=_TENANT,
        code=code,
        name=name,
        storage_key="tenants/t1/templates/instr.docx",
        status=TemplateStatus.ACTIVE,
    )
    session.add(row)
    await session.flush()
    return row


async def _file(session, *, key="tenants/t1/docs/1.pdf", payload=b"PDF-BYTES", size=None):
    row = File(
        tenant_id=_TENANT,
        storage_key=key,
        bucket="ptd",
        sha256="a" * 64,
        size=size if size is not None else len(payload or b""),
        mime="application/pdf",
        original_name="prikaz.pdf",
        kind=FileKind.DOCUMENT,
        is_quarantined=False,
        scan_status=FileScanStatus.CLEAN,
    )
    session.add(row)
    await session.flush()
    if payload is not None:
        FileStorageService.default().put(key, payload, content_type="application/pdf")
    return row


async def _document(session, env, template, *, status=DocumentStatus.SIGNED, file=None):
    row = Document(
        tenant_id=_TENANT,
        company_id=env.company.id,
        person_id=env.person.id,
        template_id=template.id,
        status=status,
        file_id=file.id if file is not None else None,
        created_by="specialist-of-outsourcer",
        content_sha256="b" * 64,
    )
    session.add(row)
    await session.flush()
    return row


async def _transfer(session, mcid):
    with patch.object(routes, "_trusted_session", lambda: _TrustedWrapper(session)):
        return await routes.transfer_client_data(
            mcid=mcid,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )


async def _target_id(session) -> str:
    row = (await session.execute(select(Tenant).where(Tenant.slug == "romashka"))).scalar_one()
    return row.id


@pytest.mark.asyncio
async def test_documents_travel_with_file_and_client_owner_as_author(sessionmaker):
    async with sessionmaker() as session:
        env = await _setup(session)
        template = await _template(session)
        src_file = await _file(session)
        await _document(session, env, template, file=src_file)

        out = await _transfer(session, env.client.id)
        assert out.counts["documents"] == 1
        assert out.counts["files"] == 1
        assert out.counts["template_stubs"] == 1

        target = await _target_id(session)
        doc = (
            await session.execute(select(Document).where(Document.tenant_id == target))
        ).scalar_one()
        owner = (
            await session.execute(
                select(User).where(User.tenant_id == target, User.role == RoleEnum.OWNER)
            )
        ).scalar_one()
        new_file = (
            await session.execute(select(File).where(File.tenant_id == target))
        ).scalar_one()

        # Авторство — владелец клиента (решение владельца 2026-08-08).
        assert doc.created_by == owner.id
        # Статус готового документа сохраняется: «подписан» не превращается в
        # «архив», иначе клиент решит, что приказ не действует.
        assert doc.status == DocumentStatus.SIGNED
        assert doc.file_id == new_file.id
        # У копии СВОЙ объект хранилища в префиксе нового арендатора.
        assert new_file.storage_key != src_file.storage_key
        assert new_file.storage_key.startswith("tenants/romashka/transferred/")
        assert FileStorageService.default().get(new_file.storage_key) == b"PDF-BYTES"
        # Исходный объект остался на месте — это копия, а не переезд.
        assert FileStorageService.default().get(src_file.storage_key) == b"PDF-BYTES"


@pytest.mark.asyncio
async def test_template_travels_as_stub_without_body(sessionmaker):
    """Тело шаблона — методика аутсорсера; едет только карточка."""

    async with sessionmaker() as session:
        env = await _setup(session)
        template = await _template(session)
        await _document(session, env, template)

        await _transfer(session, env.client.id)

        target = await _target_id(session)
        stub = (
            await session.execute(select(Template).where(Template.tenant_id == target))
        ).scalar_one()
        assert stub.name == "Инструкция по ОТ"
        assert stub.storage_key is None
        assert stub.current_version_id is None
        assert stub.status == TemplateStatus.ARCHIVED
        assert stub.metadata_json["transferred_stub"] is True


@pytest.mark.asyncio
async def test_unfinished_documents_stay_and_are_counted(sessionmaker):
    """Черновик и «на проверке» — работа аутсорсера в процессе."""

    async with sessionmaker() as session:
        env = await _setup(session)
        template = await _template(session)
        await _document(session, env, template, status=DocumentStatus.DRAFT)
        await _document(session, env, template, status=DocumentStatus.REVIEW)
        await _document(session, env, template, status=DocumentStatus.APPROVED)

        out = await _transfer(session, env.client.id)
        assert out.counts["documents"] == 1
        assert out.counts["documents_unfinished_skipped"] == 2

        target = await _target_id(session)
        rows = (
            (await session.execute(select(Document).where(Document.tenant_id == target)))
            .scalars()
            .all()
        )
        assert [row.status for row in rows] == [DocumentStatus.APPROVED]


@pytest.mark.asyncio
async def test_missing_storage_object_is_counted_not_faked(sessionmaker):
    """Строка файла есть, объекта нет: «файл» без содержимого — обман."""

    async with sessionmaker() as session:
        env = await _setup(session)
        template = await _template(session)
        ghost = await _file(session, key="tenants/t1/docs/ghost.pdf", payload=None)
        await _document(session, env, template, file=ghost)

        out = await _transfer(session, env.client.id)
        assert out.counts["files"] == 0
        assert out.counts["files_skipped"] == 1
        assert out.counts["documents"] == 1

        target = await _target_id(session)
        doc = (
            await session.execute(select(Document).where(Document.tenant_id == target))
        ).scalar_one()
        assert doc.file_id is None


@pytest.mark.asyncio
async def test_without_tenant_owner_documents_are_not_invented(sessionmaker):
    """Без владельца записывать авторство не на кого — и мы не выдумываем."""

    async with sessionmaker() as session:
        env = await _setup(session, with_owner=False)
        template = await _template(session)
        await _document(session, env, template)

        out = await _transfer(session, env.client.id)
        assert out.counts["documents_skipped_no_owner"] == 1
        assert "documents" not in out.counts

        target = await _target_id(session)
        rows = (
            (await session.execute(select(Document).where(Document.tenant_id == target)))
            .scalars()
            .all()
        )
        assert rows == []


@pytest.mark.asyncio
async def test_pdn_consents_stay_with_the_outsourcer_and_are_counted(sessionmaker):
    """Решение владельца (2026-08-08): клиент собирает согласия заново.

    Причина не техническая: согласие даётся КОНКРЕТНОМУ оператору на конкретные
    цели. Переписать его на другого оператора — подделка основания обработки.
    Поэтому согласия не едут, но и не молчат: их видно числом.
    """

    from app.models.privacy_consents import PdnConsent

    async with sessionmaker() as session:
        env = await _setup(session)
        session.add(
            PdnConsent(
                tenant_id=_TENANT,
                subject_person_id=env.person.id,
                purpose="occupational_safety",
                legal_basis="consent",
                status="active",
                granted_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["pdn_consents_left_behind"] == 1

        target = await _target_id(session)
        rows = (
            (await session.execute(select(PdnConsent).where(PdnConsent.tenant_id == target)))
            .scalars()
            .all()
        )
        assert rows == []


@pytest.mark.asyncio
async def test_other_company_documents_stay(sessionmaker):
    async with sessionmaker() as session:
        env = await _setup(session)
        template = await _template(session)
        other = Company(tenant_id=_TENANT, name="ООО Чужая")
        session.add(other)
        await session.flush()
        session.add(
            Document(
                tenant_id=_TENANT,
                company_id=other.id,
                template_id=template.id,
                status=DocumentStatus.SIGNED,
                created_by="specialist-of-outsourcer",
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["documents"] == 0

        target = await _target_id(session)
        rows = (
            (await session.execute(select(Document).where(Document.tenant_id == target)))
            .scalars()
            .all()
        )
        assert rows == []
