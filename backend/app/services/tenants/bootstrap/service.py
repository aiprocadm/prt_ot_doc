from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aensure_tenant_schema
from app.domains.reseller.industries import pack_name_for
from app.domains.reseller.starter_pack import plan_starter_pack
from app.models.master_data import Position
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
from app.models.safety_core import Hazard, RiskMeasure
from app.modules.subscription.plans import DEFAULT_PLAN_CODE, PLANS
from app.services.audit import AuditService
from app.services.auth import hash_password
from app.services.authz_seed import seed_authz_catalog
from app.services.rules_library_seed import seed_rule_library
from app.services.tenants.subscription import provision_plan


def _find_repo_root() -> Path:
    """Найти корень репозитория ПО ОРИЕНТИРУ, а не по числу уровней вверх.

    Было `parents[6]` — и это промахивалось мимо корня на один уровень:
    от `backend/app/services/tenants/bootstrap/service.py` корень находится на
    `parents[5]`. Из-за промаха файл эталона не находился НИКОГДА (ни в обычной
    копии, ни в worktree), выдача каждого арендатора молча писала
    `starter_pack_missing`, и «стартовый набор» не применялся вообще.

    Счёт уровней ломается от любого переноса файла и от запуска из worktree
    (там путь длиннее). Ориентир `seed/tenant_starter_packs` устойчив к обоим
    случаям: ищем ближайшего предка, у которого он есть.
    """

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "seed" / "tenant_starter_packs").is_dir():
            return candidate
    # Ориентир не найден (обрезанная сборка) — отдаём прежнее поведение:
    # шаг посева сам сообщит `starter_pack_missing`, а выдача не упадёт.
    return here.parents[5]


ROOT = _find_repo_root()
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
        parent_id: str | None = None,
        industry: str | None = None,
        plan_code: str | None = None,
    ) -> BootstrapTenantSummary:
        summary = BootstrapTenantSummary(tenant_slug=tenant_slug, dry_run=dry_run)

        tenant = await self._ensure_tenant(
            tenant_slug=tenant_slug,
            tenant_name=tenant_name,
            owner_email=owner_email,
            dry_run=dry_run,
            summary=summary,
            parent_id=parent_id,
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
        await self._ensure_plan(
            tenant_id=tenant_id, plan_code=plan_code, dry_run=dry_run, summary=summary
        )
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
            industry=industry,
            summary=summary,
        )
        await self._seed_package_presets(tenant_id=tenant_id, dry_run=dry_run, summary=summary)
        await self._seed_rule_library(tenant_id=tenant_id, dry_run=dry_run, summary=summary)
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
        parent_id: str | None = None,
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

        # `parent_id` — владелец нового арендатора в иерархии (BIZ-52 разд. 52.1).
        # `None` означает «прямой клиент платформы» и сохраняет прежнее поведение
        # для dev/demo-бутстрапа.
        tenant = Tenant(
            slug=tenant_slug,
            code=tenant_slug,
            name=tenant_name,
            contact_email=owner_email,
            parent_id=parent_id,
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

    async def _ensure_plan(
        self,
        *,
        tenant_id: str,
        plan_code: str | None,
        dry_run: bool,
        summary: BootstrapTenantSummary,
    ) -> None:
        """Выдать новому арендатору тариф: модули и квоты (BIZ-53 разд. 53.1).

        **До этого среза арендатор рождался БЕЗ тарифа вовсе.** Строк выдачи не
        писалось ни одной, а умолчание продаваемого модуля — «выключен»
        (BIZ-61 срез-2), поэтому новый клиент получал 404 на всех девяти
        продаваемых модулях, при том что пункты меню владелец и админ видят
        всегда (у этих ролей есть все права). Квоты при этом ставились числами
        (4 / 2500 / 5120), не совпадающими НИ С ОДНИМ тарифом, и консоль
        показывала такого арендатора как «Свой набор».

        Умолчание — самый простой тариф (решение владельца, 19.08.2026):
        ``DEFAULT_PLAN_CODE``. Константа существовала с самого начала и не
        читалась ни одной строкой кода — теперь она наконец работает.

        Квоты берутся из пресета тарифа, а не сохраняются прежними: «Базовый»
        с квотами уровня «Про» — это неверная подпись в консоли и в счёте.
        Существующих арендаторов это не касается: ветка работает только при
        заведении, у арендатора с квотой шаг идемпотентен.
        """

        existing = (
            await self.session.execute(
                select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if existing:
            summary.mark(entity="tenant_plan", created=False)
            return
        if dry_run:
            summary.mark(entity="tenant_plan", created=True)
            return

        plan = PLANS[plan_code or DEFAULT_PLAN_CODE]
        await provision_plan(self.session, tenant_id=tenant_id, plan=plan)
        summary.mark(entity="tenant_plan", created=True)

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
        # Записать СРАЗУ. В сессиях этого приложения `autoflush=False`, поэтому
        # следующий шаг (посев эталонного набора) искал организацию запросом и
        # НЕ НАХОДИЛ её — должности молча пропускались с пометкой «у арендатора
        # нет организации», хотя организация была создана строкой выше. Так
        # ломался единственный вид эталонных строк, привязанный к организации:
        # опасности и меры создавались, должности — никогда.
        await self.session.flush()
        summary.mark(entity="company_profile", created=True)

    async def _seed_starter_pack(
        self,
        *,
        tenant_id: str,
        tenant_slug: str,
        dry_run: bool,
        demo: bool,
        industry: str | None,
        summary: BootstrapTenantSummary,
    ) -> None:
        # BIZ-52 срез-12: набор выбирается отраслью. Неизвестный код долетает
        # сюда исключением — ручка переводит его в 400, а не молча выдаёт общий
        # набор под видом отраслевого.
        pack = pack_name_for(industry=industry, demo=demo)
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
        # BIZ-52 срез-7: набор становится НАСТОЯЩИМИ справочниками.
        # До этого он только клался в `settings` целым куском, который не читал
        # никто, — а отчёт при этом рапортовал «starter_pack created». Новый
        # клиент получал пустые справочники и уверенность, что они заполнены.
        await self._apply_reference_data(
            tenant_id=tenant_id, payload=payload, summary=summary
        )
        summary.mark(entity="starter_pack", created=True)

    async def apply_config(
        self, *, tenant_id: str, payload: dict[str, Any]
    ) -> BootstrapTenantSummary:
        """Применить набор к УЖЕ существующему арендатору (BIZ-52 срез-16).

        Перенос конфигурации между клиентами использует ровно тот же посев, что
        и выдача нового арендатора: своя копия применения разошлась бы с этой
        при первой же правке, и «перенесённое» начало бы отличаться от
        «выданного при создании».

        Возвращает тот же отчёт, что и выдача, — с предупреждениями о
        неприменимых видах.
        """

        summary = BootstrapTenantSummary(tenant_slug=tenant_id, dry_run=False)
        await self._apply_reference_data(
            tenant_id=tenant_id, payload=payload, summary=summary
        )
        await self.session.commit()
        return summary

    async def _apply_reference_data(
        self, *, tenant_id: str, payload: dict[str, Any], summary: BootstrapTenantSummary
    ) -> None:
        """Создать справочники эталона строками. Идемпотентно по названию.

        Идемпотентность обязательна: выдача арендатора повторяется (ретрай,
        повторный вызов bootstrap), и второй проход не должен удваивать
        справочник. Совпадение ищется по названию без учёта регистра — ровно
        так же, как схлопываются дубли внутри самого файла.

        Пропуски объявляются ЯВНО (`starter_pack_skipped:...`): половина ключей
        файла называет перечисления в коде, а не таблицы, и молчание об этом
        читалось бы как потеря данных.
        """

        plan = plan_starter_pack(payload)
        for kind, reason in plan.skipped.items():
            summary.warnings.append(f"starter_pack_skipped:{kind}:{reason}")
        for kind in plan.unknown:
            summary.warnings.append(f"starter_pack_unknown_kind:{kind}")
        if not plan.apply:
            return

        company_id: str | None = None
        if "positions" in plan.apply:
            # Должность требует организацию (FK NOT NULL). Её создаёт шаг
            # `_ensure_company_profile` прямо перед этим — но если организации
            # нет (например, она уже была и запрос её не нашёл), должности
            # молча пропускаются С ПОМЕТКОЙ, а не роняют выдачу арендатора.
            company_id = await self.session.scalar(
                select(Company.id).where(Company.tenant_id == tenant_id).limit(1)
            )
            if company_id is None:
                summary.warnings.append(
                    "starter_pack_skipped:positions:у арендатора нет организации"
                )

        created_any = False
        for kind, names in plan.apply.items():
            if kind == "positions":
                if company_id is None:
                    continue
                created_any |= await self._seed_positions(tenant_id, company_id, names)
            elif kind == "hazards":
                created_any |= await self._seed_named(tenant_id, names, Hazard)
            elif kind == "controls":
                created_any |= await self._seed_named(tenant_id, names, RiskMeasure)
        if created_any:
            await self.session.flush()

    async def _seed_positions(
        self, tenant_id: str, company_id: str, names: list[str]
    ) -> bool:
        existing = {
            str(name).casefold()
            for name in (
                await self.session.execute(
                    select(Position.name).where(Position.tenant_id == tenant_id)
                )
            ).scalars()
        }
        created = False
        for name in names:
            if name.casefold() in existing:
                continue
            self.session.add(
                Position(tenant_id=tenant_id, company_id=company_id, name=name)
            )
            existing.add(name.casefold())
            created = True
        return created

    async def _seed_named(self, tenant_id: str, names: list[str], model: Any) -> bool:
        """Создать строки справочника «одно название — одна строка».

        Одна функция на опасности и меры: у обеих таблиц из обязательного —
        только `name`, и две почти одинаковые копии разъехались бы при первой
        же правке.

        **Вставка идёт ЯВНЫМ списком колонок, а не через ORM-объект.** У обеих
        таблиц есть необязательная колонка-перечисление (`hazards.source_type`,
        `risk_measures.measure_type`). ORM включает в INSERT ВСЕ колонки, и
        SQLAlchemy приводит их к типу: `$5::hazardsourcetype`. Выдача арендатора
        идёт доверенной сессией (`tenant="public"`, `rls_bypass`) — у неё пустой
        search_path, тип PG по имени не находится, и вставка падает
        «type hazardsourcetype does not exist». Таблица при этом резолвится:
        ломается именно приведение типа. Явный список колонок обходит это
        полностью и не зависит от того, как настроен search_path у вызывающего.
        Поймано db-гейтом на живом PostgreSQL — на SQLite перечислений нет, и
        обычный прогон был зелёным.
        """

        existing = {
            str(name).casefold()
            for name in (
                await self.session.execute(
                    select(model.name).where(model.tenant_id == tenant_id)
                )
            ).scalars()
        }
        rows: list[dict[str, Any]] = []
        now = datetime.now(tz=timezone.utc)
        for name in names:
            if name.casefold() in existing:
                continue
            existing.add(name.casefold())
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "name": name,
                    "created_at": now,
                    "updated_at": now,
                    "version": 1,
                }
            )
        if not rows:
            return False
        await self.session.execute(insert(model.__table__), rows)
        return True

    async def _seed_rule_library(
        self, *, tenant_id: str, dry_run: bool, summary: BootstrapTenantSummary
    ) -> None:
        """Библиотека правил по дисциплинам (BIZ-54-57 срез-4, разд. 57.3).

        Сверка нашла: движок правил был, а предустановленных правил — ни одного.
        Два правила существовали только у демо-арендатора, прямо в коде демо-
        посева; настоящий новый клиент получал пустой движок и должен был
        придумывать экспертизу сам.

        Выдаётся ВСЕМ, включая арендаторов без купленного модуля: движок сам
        проверяет модуль перед срабатыванием, поэтому у них правила лежат и
        молчат. Иначе купивший модуль позже получил бы пустой движок.
        """

        if dry_run:
            summary.mark(entity="rule_library", created=True)
            return
        created = await seed_rule_library(self.session, tenant_id=tenant_id)
        summary.mark(entity="rule_library", created=bool(created))

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
