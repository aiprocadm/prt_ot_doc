from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aensure_tenant_schema
from app.models.models import (
    Company,
    PackagePreset,
    PackageProfile,
    RoleEnum,
    Tenant,
    TenantQuota,
    TenantSettings,
    User,
    UserRole,
)
from app.services.audit import AuditService
from app.services.auth import hash_password
from app.services.authz_seed import seed_authz_catalog

ROOT = Path(__file__).resolve().parents[6]
STARTER_PACK_ROOT = ROOT / "seed" / "tenant_starter_packs"


@dataclass(slots=True)
class BootstrapTenantSummary:
    tenant_slug: str
    dry_run: bool
    created: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def mark(self, *, entity: str, created: bool) -> None:
        (self.created if created else self.reused).append(entity)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BootstrapTenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(
        self,
        *,
        tenant_slug: str,
        tenant_name: str,
        owner_email: str,
        owner_password: str,
        dry_run: bool = False,
        demo: bool = False,
    ) -> BootstrapTenantSummary:
        summary = BootstrapTenantSummary(tenant_slug=tenant_slug, dry_run=dry_run)

        tenant = await self._ensure_tenant(
            tenant_slug=tenant_slug,
            tenant_name=tenant_name,
            owner_email=owner_email,
            dry_run=dry_run,
            summary=summary,
        )
        tenant_id = tenant.id if tenant else f"dry-run:{tenant_slug}"
        tenant_schema = tenant.schema_name if tenant else f"tenant_{tenant_slug}"

        await self._ensure_tenant_settings(
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            tenant_schema=tenant_schema,
            dry_run=dry_run,
            summary=summary,
        )
        await self._ensure_quota(tenant_id=tenant_id, dry_run=dry_run, summary=summary)
        await self._ensure_owner(
            tenant_id=tenant_id,
            owner_email=owner_email,
            owner_password=owner_password,
            dry_run=dry_run,
            summary=summary,
        )
        if not dry_run:
            await seed_authz_catalog(self.session, tenant_id=tenant_id)
        summary.mark(entity="authz_catalog", created=False)
        await self._ensure_company_profile(
            tenant_id=tenant_id, tenant_name=tenant_name, dry_run=dry_run, summary=summary
        )
        await self._seed_starter_pack(
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            dry_run=dry_run,
            demo=demo,
            summary=summary,
        )
        await self._seed_package_presets(tenant_id=tenant_id, dry_run=dry_run, summary=summary)
        await self._log_bootstrap_event(
            tenant_id=tenant_id, tenant_slug=tenant_slug, dry_run=dry_run, summary=summary
        )

        if not dry_run:
            await self.session.flush()
        return summary

    async def _ensure_tenant(
        self,
        *,
        tenant_slug: str,
        tenant_name: str,
        owner_email: str,
        dry_run: bool,
        summary: BootstrapTenantSummary,
    ) -> Tenant | None:
        existing = (
            await self.session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if existing:
            await aensure_tenant_schema(
                existing.slug, schema_name=existing.schema_name or f"tenant_{existing.slug}"
            )
            summary.mark(entity="tenant", created=False)
            return existing

        if dry_run:
            summary.mark(entity="tenant", created=True)
            return None

        tenant = Tenant(
            slug=tenant_slug,
            code=tenant_slug,
            name=tenant_name,
            contact_email=owner_email,
            schema_name=f"tenant_{tenant_slug}",
            s3_prefix=f"tenants/{tenant_slug}",
        )
        self.session.add(tenant)
        await self.session.flush()
        await aensure_tenant_schema(tenant_slug, schema_name=tenant.schema_name)
        summary.mark(entity="tenant", created=True)
        return tenant

    async def _ensure_tenant_settings(
        self,
        *,
        tenant_id: str,
        tenant_slug: str,
        tenant_schema: str,
        dry_run: bool,
        summary: BootstrapTenantSummary,
    ) -> None:
        existing = (
            await self.session.execute(
                select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if existing:
            summary.mark(entity="tenant_settings", created=False)
            return
        if dry_run:
            summary.mark(entity="tenant_settings", created=True)
            return
        self.session.add(
            TenantSettings(
                tenant_id=tenant_id,
                schema_name=tenant_schema,
                s3_prefix=f"tenants/{tenant_slug}",
                retention_policy={"audit_days": 3650},
            )
        )
        summary.mark(entity="tenant_settings", created=True)

    async def _ensure_quota(
        self, *, tenant_id: str, dry_run: bool, summary: BootstrapTenantSummary
    ) -> None:
        existing = (
            await self.session.execute(
                select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if existing:
            summary.mark(entity="tenant_quota", created=False)
            return
        if dry_run:
            summary.mark(entity="tenant_quota", created=True)
            return
        self.session.add(
            TenantQuota(
                tenant_id=tenant_id,
                max_parallel_jobs=4,
                max_doc_generations_per_month=2500,
                max_storage_mb=5120,
                enforce_billing_gate=False,
            )
        )
        summary.mark(entity="tenant_quota", created=True)

    async def _ensure_owner(
        self,
        *,
        tenant_id: str,
        owner_email: str,
        owner_password: str,
        dry_run: bool,
        summary: BootstrapTenantSummary,
    ) -> None:
        existing = (
            await self.session.execute(
                select(User).where(
                    User.tenant_id == tenant_id, func.lower(User.email) == owner_email.lower()
                )
            )
        ).scalar_one_or_none()
        if existing:
            summary.mark(entity="owner_user", created=False)
            return
        if dry_run:
            summary.mark(entity="owner_user", created=True)
            return

        user = User(
            tenant_id=tenant_id,
            email=owner_email.lower(),
            full_name="Tenant Owner",
            role=RoleEnum.OWNER,
            hashed_password=hash_password(owner_password),
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()
        self.session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role=RoleEnum.OWNER))
        self.session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role=RoleEnum.ADMIN))
        summary.mark(entity="owner_user", created=True)

    async def _ensure_company_profile(
        self, *, tenant_id: str, tenant_name: str, dry_run: bool, summary: BootstrapTenantSummary
    ) -> None:
        existing = (
            (await self.session.execute(select(Company).where(Company.tenant_id == tenant_id)))
            .scalars()
            .first()
        )
        if existing:
            summary.mark(entity="company_profile", created=False)
            return
        if dry_run:
            summary.mark(entity="company_profile", created=True)
            return
        self.session.add(Company(tenant_id=tenant_id, name=tenant_name, legal_address="TBD"))
        summary.mark(entity="company_profile", created=True)

    async def _seed_starter_pack(
        self,
        *,
        tenant_id: str,
        tenant_slug: str,
        dry_run: bool,
        demo: bool,
        summary: BootstrapTenantSummary,
    ) -> None:
        pack = "demo" if demo else "default"
        path = STARTER_PACK_ROOT / "v1" / f"{pack}.json"
        if not path.exists():
            summary.warnings.append(f"starter_pack_missing:{path}")
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        existing = (
            await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if (
            existing
            and isinstance(existing.settings, dict)
            and existing.settings.get("starter_pack")
        ):
            summary.mark(entity="starter_pack", created=False)
            return
        if dry_run:
            summary.mark(entity="starter_pack", created=True)
            return
        if existing is not None:
            existing.settings = {
                **(existing.settings or {}),
                "starter_pack": payload,
                "bootstrap_state": {
                    "configured": False,
                    "remaining_actions": [
                        "setup_sites",
                        "import_employees",
                        "configure_integrations",
                    ],
                },
                "storage_prefixes": [
                    f"tenants/{tenant_slug}/exports",
                    f"tenants/{tenant_slug}/uploads",
                    f"tenants/{tenant_slug}/archives",
                ],
            }
        summary.mark(entity="starter_pack", created=True)

    async def _seed_package_presets(
        self, *, tenant_id: str, dry_run: bool, summary: BootstrapTenantSummary
    ) -> None:
        defaults = [
            ("Выход на объект", "Выход на объект", "site-exit"),
            ("Несчастный случай", "Несчастный случай", "incident"),
            ("Подготовка к проверке", "Подготовка к проверке", "inspection-prep"),
            ("Обучение", "Обучение", "training"),
        ]
        created_any = False
        for profile_name, preset_name, code in defaults:
            profile = (
                await self.session.execute(
                    select(PackageProfile).where(
                        PackageProfile.tenant_id == tenant_id, PackageProfile.name == profile_name
                    )
                )
            ).scalar_one_or_none()
            if profile is None and not dry_run:
                profile = PackageProfile(
                    tenant_id=tenant_id,
                    name=profile_name,
                    description=f"Стартовый профиль: {profile_name}",
                    config={"code": code},
                )
                self.session.add(profile)
                await self.session.flush()
                created_any = True
            existing = (
                await self.session.execute(
                    select(PackagePreset).where(
                        PackagePreset.tenant_id == tenant_id, PackagePreset.name == preset_name
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            if dry_run:
                continue
            if profile is None:
                continue  # defensive: profile missing and not created (e.g. add() not flushed yet)
            self.session.add(
                PackagePreset(
                    tenant_id=tenant_id,
                    profile_id=profile.id,
                    name=preset_name,
                    payload={"profile": code, "checklist": []},
                )
            )
            created_any = True
        summary.mark(entity="package_presets", created=created_any or dry_run)

    async def _log_bootstrap_event(
        self, *, tenant_id: str, tenant_slug: str, dry_run: bool, summary: BootstrapTenantSummary
    ) -> None:
        if dry_run:
            summary.mark(entity="audit_event", created=True)
            return
        await AuditService(self.session).log_event(
            tenant_id=tenant_id,
            action="tenant.bootstrap.completed",
            object_type="tenant",
            object_id=tenant_id,
            user_id=None,
            ip="127.0.0.1",
            actor_type="system",
            actor_email="bootstrap@system.local",
            details={
                "tenant_slug": tenant_slug,
                "created": summary.created,
                "reused": summary.reused,
            },
        )
        summary.mark(entity="audit_event", created=True)
