"""OPS-72 (разд. 72.3): офбординг — grace-период и план удаления.

ТЗ требует четырёх вещей, и все четыре здесь разные:

* **grace-период** — после расторжения данные хранятся N дней «на случай возврата
  или споров»;
* **юридические исключения** — «что закон требует хранить дольше, не удалять
  слепо». Сроки не изобретаются заново: они уже лежат данными в
  ``pdn_processing_activity.retention_months`` (SEC-66 срез-3), где у каждого
  процесса обработки указан срок ВМЕСТЕ со ссылкой на норму;
* **обезличивание вместо удаления** — там, где нужно сохранить статистику без ПДн;
* **акт** — подтверждение, что именно удалено.

Здесь — **план**, который утверждает человек; исполнение живёт отдельно
(``purge.py``), и это разделение намеренное: необратимую операцию запускают по
утверждённому плану, а не «посмотрим, что получится».

**План обязан совпадать с исполнением.** Поэтому срок хранения «протекает» вверх
по внешним ключам уже в плане: если удерживается ``medical_exam``, удалить
``person``, на которого он ссылается, невозможно — значит человек должен видеть
``person`` в строке «обезличить», а не узнать об этом из отчёта постфактум.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offboarding import TenantOffboarding
from app.models.privacy_registry import PdnProcessingActivity
from app.modules.offboarding.schema_graph import SchemaGraph, reflect_schema_graph

__all__ = [
    "TenantOffboardingService",
    "PurgePlan",
    "TablePlan",
    "ACTIVITY_TABLES",
    "DEFAULT_GRACE_DAYS",
    "OffboardingStateError",
]

DEFAULT_GRACE_DAYS = 30


class OffboardingStateError(RuntimeError):
    """Недопустимый переход состояния офбординга."""


# Какие таблицы покрывает каждый процесс реестра обработки (SEC-66 срез-3).
# Карта намеренно ЯВНАЯ и короткая: срок хранения — юридическое решение, и оно
# должно быть читаемым при ревью, а не выводиться эвристикой по имени таблицы.
# Таблица, не попавшая ни в один процесс, планируется к удалению: у неё нет
# основания храниться дольше.
ACTIVITY_TABLES: dict[str, tuple[str, ...]] = {
    "hr_records": ("person", "person_compliance_read_models"),
    "medical_exams": (
        "medical_exam",
        "medical_referral",
        "medical_suspension",
        "medical_factor",
    ),
    "occupational_safety": (
        "briefing_entries",
        "briefing_signatures",
        "ppeissue",
        "risk_assessments",
    ),
    "training": ("training_session", "training_certificates", "training_protocols"),
    "incidents": ("incident", "incident_investigations", "incident_persons"),
}


@dataclass
class TablePlan:
    table: str
    rows: int
    action: str  # delete | anonymize
    reason: str


@dataclass
class PurgePlan:
    tenant_id: str
    tenant_slug: str
    generated_at: datetime
    grace_until: datetime
    grace_expired: bool
    tables: list[TablePlan]

    @property
    def rows_to_delete(self) -> int:
        return sum(item.rows for item in self.tables if item.action == "delete")

    @property
    def rows_to_anonymize(self) -> int:
        return sum(item.rows for item in self.tables if item.action == "anonymize")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant_slug,
            "generated_at": self.generated_at.isoformat(),
            "grace_until": self.grace_until.isoformat(),
            "grace_expired": self.grace_expired,
            "rows_to_delete": self.rows_to_delete,
            "rows_to_anonymize": self.rows_to_anonymize,
            "tables": [
                {
                    "table": item.table,
                    "rows": item.rows,
                    "action": item.action,
                    "reason": item.reason,
                }
                for item in self.tables
            ],
        }


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class TenantOffboardingService:
    """Заявка, отмена и план удаления (разд. 72.3)."""

    def __init__(self, session: AsyncSession, *, tenant_id: str, tenant_slug: str) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)
        self.tenant_slug = tenant_slug

    async def current(self) -> TenantOffboarding | None:
        """Актуальная заявка: незакрытая, иначе последняя по времени."""

        rows = (
            (
                await self.session.execute(
                    select(TenantOffboarding)
                    .where(TenantOffboarding.tenant_id == self.tenant_id)
                    .order_by(TenantOffboarding.requested_at.desc())
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.status == "grace":
                return row
        return rows[0] if rows else None

    async def request(
        self,
        *,
        reason: str | None = None,
        grace_days: int = DEFAULT_GRACE_DAYS,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> TenantOffboarding:
        """Подать заявку. Повторная заявка при активном grace — не ошибка, а та же
        заявка: клиент, нажавший кнопку дважды, не должен обнулять себе срок."""

        existing = await self.current()
        if existing is not None and existing.status == "grace":
            return existing

        # Срез-190: партнёр с живыми клиентами не уходит молча. Подробности
        # решения — в блоке «каскад по иерархии» в конце модуля.
        dependents = await active_dependents(self.session, tenant_id=self.tenant_id)
        if dependents:
            raise DependentTenantsError(dependents)

        now = _utcnow()
        record = TenantOffboarding(
            tenant_id=self.tenant_id,
            status="grace",
            reason=reason,
            requested_at=now,
            grace_days=max(0, int(grace_days)),
            grace_until=now + timedelta(days=max(0, int(grace_days))),
            requested_by_user_id=str(actor_user_id) if actor_user_id else None,
            requested_by_email=actor_email,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def cancel(self, *, reason: str | None = None) -> TenantOffboarding | None:
        """Клиент вернулся. Запись не удаляется: история расторжений — часть
        ответа на «что происходило с нашими данными»."""

        record = await self.current()
        if record is None or record.status != "grace":
            return None
        record.status = "cancelled"
        record.cancelled_at = _utcnow()
        if reason:
            record.reason = f"{record.reason or ''}\nОтмена: {reason}".strip()
        await self.session.flush()
        return record

    async def _retained_tables(self) -> dict[str, str]:
        """Таблицы под действующим сроком хранения → обоснование.

        Источник — реестр обработки (SEC-66 срез-3): у каждого процесса указан
        срок В МЕСЯЦАХ вместе со ссылкой на норму. Заводить отдельный справочник
        сроков значит завести второй источник правды, который разъедется с первым.
        """

        activities = (
            (
                await self.session.execute(
                    select(PdnProcessingActivity).where(
                        PdnProcessingActivity.tenant_id == self.tenant_id,
                        PdnProcessingActivity.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        retained: dict[str, str] = {}
        for activity in activities:
            months = activity.retention_months
            if not months:
                continue
            basis = activity.retention_basis or "срок хранения задан без ссылки на норму"
            for table in ACTIVITY_TABLES.get(activity.code, ()):
                retained[table] = f"{activity.name}: {months} мес. — {basis}"
        return retained

    async def schema_graph(self) -> SchemaGraph:
        """Живая схема арендатора: какие tenant-таблицы есть и как связаны."""

        from app.core.rls_policy import RLS_ENABLED_TABLES

        return await reflect_schema_graph(self.session, RLS_ENABLED_TABLES)

    async def retained_tables(self) -> dict[str, str]:
        """Таблицы, которые НЕ удаляются, с обоснованием у каждой.

        Два источника, и оба обязательны:

        1. прямой срок хранения из реестра обработки (SEC-66 срез-3);
        2. **протекание срока вверх по ссылкам**: родителя удерживаемой записи
           удалить нельзя — внешний ключ не даст, а если бы дал, остались бы
           сироты. Это должно быть видно в плане, а не всплыть при исполнении.
        """

        direct = await self._retained_tables()
        graph = await self.schema_graph()
        retained = {table: reason for table, reason in direct.items() if table in graph.tables}
        for parent, child in graph.retention_closure(retained).items():
            retained.setdefault(
                parent,
                f"хранится вместе с «{child}»: удалить родителя удерживаемой записи нельзя",
            )
        return retained

    async def build_purge_plan(self) -> PurgePlan:
        """Что будет удалено, что обезличено и на каком основании."""

        record = await self.current()
        grace_until = record.grace_until if record else _utcnow()
        retained = await self.retained_tables()
        graph = await self.schema_graph()

        plans: list[TablePlan] = []
        for table in graph.tables:
            rows = (
                await self.session.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE tenant_id = :tenant'),
                    {"tenant": self.tenant_id},
                )
            ).scalar_one()
            if not rows:
                continue
            basis = retained.get(table)
            plans.append(
                TablePlan(
                    table=table,
                    rows=int(rows),
                    action="anonymize" if basis else "delete",
                    reason=basis or "нет действующего срока хранения — данные удаляются",
                )
            )

        return PurgePlan(
            tenant_id=self.tenant_id,
            tenant_slug=self.tenant_slug,
            generated_at=_utcnow(),
            grace_until=_as_utc(grace_until),
            grace_expired=_as_utc(grace_until) <= _utcnow(),
            tables=plans,
        )


# ---------------------------------------------------------------------------
# OPS-72 разд. 72.3 (срез-190): каскад по иерархии.
# ---------------------------------------------------------------------------
#
# Строка держала остаток «каскад по иерархии (BIZ-52)»: он ждал самой иерархии.
# Иерархия есть (партнёр -> его клиенты), и вопрос стал конкретным: что
# происходит с клиентами, когда уходит ПАРТНЁР.
#
# РЕШЕНИЕ (2026-09-14, делегировано владельцем): НЕ каскадное удаление, а
# ОТКАЗ со списком.
#
# Почему не каскад. Клиенты партнёра — самостоятельные организации со своими
# договорами и своими 152-ФЗ обязательствами. Удалить их данные потому, что их
# продавец расторг договор с платформой, значит принять решение за них. Ошибка
# здесь необратима: восстановить удалённое нечем.
#
# Почему не «молча разрешить». Удалённый партнёр оставляет клиентов сиротами:
# у них остаётся родитель, которого нет, наследование бренда ведёт в никуда, а
# отвечать на их обращения некому.
#
# Поэтому: заявка партнёра с живыми клиентами ОТКЛОНЯЕТСЯ и называет их
# поимённо. Владелец платформы решает, что с ними — перевести другому партнёру
# или офбордить каждого отдельно, его собственным решением.


class DependentTenantsError(OffboardingStateError):
    """У арендатора есть живые клиенты: удалять его рано."""

    def __init__(self, slugs: list[str]) -> None:
        self.slugs = slugs
        listed = ", ".join(slugs[:10]) + (" и др." if len(slugs) > 10 else "")
        super().__init__(
            "Нельзя расторгнуть договор с партнёром, пока у него есть действующие "
            f"клиенты ({len(slugs)}): {listed}. Переведите их другому партнёру или "
            "офбордите каждого отдельным решением — удалять их данные вместе с "
            "партнёром платформа не вправе."
        )


async def active_dependents(session: AsyncSession, *, tenant_id: str) -> list[str]:
    """Слаги живых клиентов арендатора.

    Живой — это не находящийся в офбординге: арендатор, который сам уже уходит,
    не должен удерживать партнёра.
    """

    from app.models.models import Tenant  # noqa: PLC0415 - цикл импорта

    children = (
        (await session.execute(select(Tenant).where(Tenant.parent_id == str(tenant_id))))
        .scalars()
        .all()
    )
    if not children:
        return []

    child_ids = [str(child.id) for child in children]
    rows = (
        (
            await session.execute(
                select(TenantOffboarding).where(
                    TenantOffboarding.tenant_id.in_(child_ids),
                    TenantOffboarding.status.in_(("grace", "purged")),
                )
            )
        )
        .scalars()
        .all()
    )
    gone = {str(row.tenant_id) for row in rows}
    return sorted(str(child.slug or child.id) for child in children if str(child.id) not in gone)
