"""Seed database with initial template data."""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
from typing import Any

from docx import Document
from sqlalchemy import select

from app.core.tenant import tenant_context
from app.db import ensure_tenant_schema, session_scope
from app.models.models import Tenant
from app.repository import create_template
from app.schemas.template import TemplateCreate
from app.services.file_storage import FileStorageService

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SEED_TENANT = os.environ.get("SEED_TENANT", "seed")
SEED_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "welcome",
        "description": "Welcome letter",
        "metadata": {"category": "onboarding"},
        "content": ["Здравствуйте {{ name }}", "Добро пожаловать в компанию."],
    },
    {
        "name": "safety-briefing",
        "description": "Инструктаж по охране труда",
        "metadata": {"category": "safety"},
        "content": [
            "Утверждено к применению.",
            "Дата проведения: {{ date }}",
        ],
    },
]


def build_docx(paragraphs: list[str]) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def ensure_tenant_exists() -> None:
    async with session_scope(tenant="public") as session:
        existing = (
            await session.execute(
                select(Tenant).where(Tenant.slug == SEED_TENANT)
            )
        ).scalar_one_or_none()
        if existing is None:
            tenant = Tenant(
                slug=SEED_TENANT,
                name=f"Seed {SEED_TENANT}",
                contact_email="seed@example.com",
                is_active=True,
            )
            session.add(tenant)
            await session.flush()
    ensure_tenant_schema(SEED_TENANT)


async def run() -> None:
    await ensure_tenant_exists()
    storage = FileStorageService.default()
    with tenant_context(SEED_TENANT):
        async with session_scope(tenant=SEED_TENANT) as session:
            for template_data in SEED_TEMPLATES:
                content_bytes = build_docx(template_data["content"])
                storage_key = f"{SEED_TENANT}/templates/{template_data['name']}.docx"
                storage.put(storage_key, content_bytes, content_type=DOCX_MIME)
                checksum = hashlib.sha256(content_bytes).digest()
                payload = TemplateCreate(
                    name=template_data["name"],
                    description=template_data["description"],
                    metadata=template_data["metadata"],
                )
                try:
                    await create_template(
                        session,
                        payload,
                        storage_key=storage_key,
                        checksum=checksum,
                    )
                except ValueError:
                    continue


if __name__ == "__main__":
    asyncio.run(run())
