"""Срез-139: у документа не бывает состояния «генерируется».

Живая генерация (PipelineRun, ``app.tasks.document_jobs``) создаёт строку
``Document`` только по завершении — уже как GENERATED; упавший прогон строки не
создаёт вовсе. Прежние ветки «генерируется»/«ошибка генерации» в списке
документов и в службе готовности читали ``DocumentGenerationJob`` — таблицу, в
которую никто не пишет, — и не срабатывали никогда. Контур снят целиком.

Здесь закреплено, что осталось честного:
  * ``?status=generating`` — 200 и ПУСТОЙ список (а не «все документы», как
    было бы для неизвестного значения);
  * ``?status=error`` — только отозванные;
  * ни один документ не показывается со статусом «generating»;
  * сторож: код документов и готовности не читает снятую связь ``.job``.
"""

from __future__ import annotations

import ast
import pathlib
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import issue_access_token
from app.models.document import DocumentStatus
from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCUMENT_READERS = (
    REPO / "backend" / "app" / "api" / "routes" / "documents" / "read.py",
    REPO / "backend" / "app" / "services" / "document_readiness.py",
)


async def _seed(
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> dict[str, str]:
    """Три документа одного арендатора: черновик, готовый, отозванный."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant, email=f"{uuid4()}@example.com", role=RoleEnum.ADMIN, session=session
        )
        company = await data_factory.create_company(
            tenant=tenant, name=f"Company {uuid4()}"[:36], session=session
        )
        template = await data_factory.create_template(
            tenant=tenant, name=f"Template {uuid4()}"[:36], session=session
        )
        ids: dict[str, str] = {}
        for status in (DocumentStatus.DRAFT, DocumentStatus.GENERATED, DocumentStatus.REVOKED):
            document, _ = await data_factory.create_document(
                tenant=tenant,
                company=company,
                person=None,
                template=template,
                creator=user,
                status=status,
                version_payload={"v": 1},
                version_file_key=f"documents/{uuid4()}.pdf",
                session=session,
            )
            ids[status.value] = document.id
        await session.commit()
        token = issue_access_token(
            subject=user.id,
            tenant=tenant.slug,
            role=user.role.value,
            additional_claims={"tenant_id": tenant.id},
        )
        return {"token": token, "slug": tenant.slug, **ids}


async def _list(client: AsyncClient, seeded: dict[str, str], **params: str) -> dict:
    response = await client.get(
        "/api/v1/documents",
        params=params,
        headers={"Authorization": f"Bearer {seeded['token']}", "X-Tenant": seeded["slug"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio()
async def test_фильтр_генерируется_честно_пуст(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed(sessionmaker, data_factory)
    body = await _list(async_client, seeded, status="generating")
    assert body["items"] == []
    assert body["pagination"]["total"] == 0


@pytest.mark.anyio()
async def test_фильтр_ошибка_это_только_отозванные(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed(sessionmaker, data_factory)
    body = await _list(async_client, seeded, status="error")
    assert {item["id"] for item in body["items"]} == {seeded["revoked"]}
    assert all(item["status"] == "error" for item in body["items"])


@pytest.mark.anyio()
async def test_статус_генерируется_не_показывается_никому(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed(sessionmaker, data_factory)
    body = await _list(async_client, seeded, page_size="200")
    statuses = {item["id"]: item["status"] for item in body["items"]}
    assert statuses[seeded["draft"]] == "draft"
    assert statuses[seeded["generated"]] == "ready"
    assert statuses[seeded["revoked"]] == "error"
    assert "generating" not in statuses.values()


def test_сторож_код_документов_не_читает_снятую_связь() -> None:
    """Связь ``Document.job`` снята вместе с контуром; вернуть её «на всякий
    случай» значит снова читать таблицу без записей."""
    offenders: list[str] = []
    for path in DOCUMENT_READERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"job", "generation_jobs"}:
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: .{node.attr}")
    assert offenders == [], "код документов снова читает снятую связь:\n" + "\n".join(offenders)
