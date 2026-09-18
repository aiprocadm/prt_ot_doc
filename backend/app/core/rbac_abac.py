from __future__ import annotations

import enum
import functools
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.errors import api_problem_detail
from app.services.audit import AuditService


class Action(str, enum.Enum):
    READ = "read"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    SIGN = "sign"
    SEND_EDO = "send_edo"
    EXPORT = "export"
    DOWNLOAD = "download"
    RUN_PIPELINE = "run_pipeline"
    RETRY_JOB = "retry_job"
    CANCEL_JOB = "cancel_job"


#: Иные написания ролей, которые может принести токен. Слева — что пришло,
#: справа — НАСТОЯЩАЯ роль продукта.
#:
#: СРЕЗ-228. Четыре записи вели на роли, которых в продукте нет. Хуже всего была
#: ``"teacher": "instructor"``: преподаватель — роль НАСТОЯЩАЯ, но нормализация
#: уводила её на выдуманного «инструктора», и вывод прав из карты (срез-227) для
#: преподавателя молча не работал — в карте такой роли нет. Он недополучал
#: шесть прав, которые карта ему даёт.
#:
#: Правило теперь одно и проверяется на импорте: синоним обязан вести на
#: существующую роль. Иначе это тихо пустые права — та же ловушка, что в
#: срезах 224, 226 и 227.
ROLE_ALIASES: dict[str, str] = {
    "tenant_owner": "owner",
    "tenant_admin": "admin",
    # HSSE — принятое в отрасли написание службы охраны труда, промышленной
    # безопасности и экологии; в продукте это руководитель ОТиПБ и его специалист.
    "hsse_head": "ot_pb_lead",
    "hsse_specialist": "ot_specialist",
    "contractor_inspector": "inspector_contractor",
    # «Методист по правовым вопросам» — в продукте это юрист.
    "methodist_legal": "lawyer",
}


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str | None
    tenant_id: str | None
    roles: tuple[str, ...]
    company_ids: tuple[str, ...] = ()
    site_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    contractor_ids: tuple[str, ...] = ()
    allowed_statuses: tuple[str, ...] = ()
    max_risk_level: int | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str
    matched_roles: tuple[str, ...] = ()
    matched_rules: tuple[str, ...] = ()
    audit_meta: dict[str, Any] = field(default_factory=dict)


def _normalize_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item)
    return ()


def _normalize_risk_level(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    mapping = {"low": 1, "medium": 2, "high": 3, "critical": 4, "crit": 4}
    if normalized in mapping:
        return mapping[normalized]
    try:
        return int(normalized)
    except ValueError:
        return None


def _normalize_role(role: str) -> str:
    normalized = str(role).lower()
    return ROLE_ALIASES.get(normalized, normalized)


def actor_from_claims(claims: dict[str, Any] | Any, roles: list[str]) -> ActorContext:
    return ActorContext(
        user_id=str(claims.get("sub") or claims.get("user_id") or "") or None,
        tenant_id=str(claims.get("tenant_id") or claims.get("tenant") or "") or None,
        roles=tuple(_normalize_role(role) for role in roles),
        company_ids=_normalize_list(claims.get("company_ids") or claims.get("company_id")),
        site_ids=_normalize_list(claims.get("site_ids") or claims.get("site_id")),
        project_ids=_normalize_list(claims.get("project_ids") or claims.get("project_id")),
        contractor_ids=_normalize_list(claims.get("contractor_ids") or claims.get("contractor_id")),
        allowed_statuses=_normalize_list(claims.get("allowed_statuses") or claims.get("statuses")),
        max_risk_level=_normalize_risk_level(claims.get("max_risk_level")),
    )


MODULE_NAMES: tuple[str, ...] = (
    "documents",
    "templates",
    "risk",
    "ppe",
    "training",
    "incidents",
    "inspections",
    "contractors",
    "reports",
    "admin",
    "briefings",
    "audit",
)

RESOURCE_PERMISSIONS: dict[str, set[str]] = {
    "templates": {"read", "list", "create", "update", "delete", "approve"},
    "template_versions": {"read", "list", "create", "update", "delete", "approve"},
    "documents": {
        "read",
        "list",
        "create",
        "update",
        "delete",
        "approve",
        "sign",
        "send_edo",
        "export",
        "download",
        "run_pipeline",
    },
    "document_versions": {"read", "list", "create", "update", "delete", "download"},
    "document_jobs": {"read", "list", "run_pipeline", "retry_job", "cancel_job"},
    "files": {"read", "list", "create", "delete", "download", "sign"},
    "package_presets": {"read", "list", "create", "update", "delete"},
    "package_profiles": {"read", "list", "create", "update", "delete"},
    "risk_maps": {"read", "list", "create", "update", "delete", "approve", "export"},
    "risk_methodologies": {"read", "list", "create", "update", "delete"},
    "ppe_norms": {"read", "list", "create", "update", "delete"},
    "ppe_issues": {"read", "list", "create", "update", "delete"},
    "warehouse_stock": {"read", "list", "create", "update", "delete"},
    "trainings": {"read", "list", "create", "update", "delete", "approve"},
    "briefings": {"read", "list", "create", "update", "delete"},
    "incidents": {"read", "list", "create", "update", "delete", "approve", "export"},
    "inspections": {"read", "list", "create", "update", "delete", "approve", "export"},
    "contractors": {"read", "list", "create", "update", "delete"},
    "reports": {"read", "list", "export", "download"},
    "admin": {"read", "list", "create", "update", "delete"},
    "data_quality": {"read"},
    "employee_card": {"read"},
    "calendar": {"read"},
}

_ROLE_FULL = {
    f"{resource}:{action}"
    for resource, actions in RESOURCE_PERMISSIONS.items()
    for action in actions
}

MODULE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(MODULE_NAMES),
    "admin": set(MODULE_NAMES),
    "lawyer": {"documents", "templates"},
    "executor": {"documents"},
    "clerk": {"documents"},
    "student": {"training"},
    "ecologist": {"documents", "risk", "incidents"},
    "hr": {"documents", "training"},
    "accountant": {"reports"},
    "line_manager": {"documents", "incidents", "inspections"},
    "client": {"documents", "reports", "contractors"},
    "auditor_ro": {"documents", "risk", "ppe", "inspections", "incidents", "reports"},
    "inspector_contractor": {"inspections", "incidents", "contractors"},
    "client_admin": {"contractors"},
    "client_user": {"contractors"},
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": _ROLE_FULL,
    "admin": _ROLE_FULL,
    "lawyer": {"documents:read", "documents:list", "templates:read", "templates:list"},
    "executor": {
        "documents:read",
        "documents:list",
        "documents:update",
        "files:read",
        "files:download",
    },
    "clerk": {
        "documents:read",
        "documents:list",
        "documents:update",
        "documents:send_edo",
        "files:read",
        "files:download",
    },
    "student": {"trainings:read", "trainings:list"},
    "ecologist": {
        "documents:read",
        "documents:list",
        "risk_maps:read",
        "risk_maps:list",
        "incidents:read",
        "incidents:list",
        "calendar:read",
    },
    "hr": {
        "documents:read",
        "documents:list",
        "trainings:read",
        "trainings:list",
        "trainings:create",
        "trainings:update",
        "data_quality:read",
        "employee_card:read",
        "calendar:read",
    },
    "accountant": {"reports:read", "reports:list", "reports:export"},
    "line_manager": {
        "documents:read",
        "documents:list",
        "documents:update",
        "incidents:read",
        "inspections:read",
        "inspections:list",
        "data_quality:read",
        "employee_card:read",
        "calendar:read",
    },
    "client": {
        "documents:read",
        "documents:list",
        "documents:download",
        "reports:read",
        "reports:list",
        "contractors:read",
        "contractors:list",
    },
    "auditor_ro": {
        "documents:read",
        "documents:list",
        "risk_maps:read",
        "risk_maps:list",
        "ppe_norms:read",
        "ppe_norms:list",
        "inspections:read",
        "inspections:list",
        "incidents:read",
        "incidents:list",
        "reports:read",
        "reports:list",
    },
    "inspector_contractor": {
        "inspections:read",
        "inspections:list",
        "incidents:read",
        "incidents:list",
        "contractors:read",
        "contractors:list",
    },
    "client_admin": {"contractors:read", "contractors:list"},
    "client_user": {"contractors:read", "contractors:list"},
}

SCOPED_RESOURCES = {
    "templates",
    "template_versions",
    "documents",
    "document_versions",
    "document_jobs",
    "files",
    "risk_maps",
    "risk_methodologies",
    "ppe_norms",
    "ppe_issues",
    "warehouse_stock",
    "trainings",
    "briefings",
    "incidents",
    "inspections",
    "contractors",
    "reports",
}


# ---------------------------------------------------------------------------
# СРЕЗ-227: права роли выводятся из ЕДИНОЙ КАРТЫ ПРАВ ЭКРАНА.
# ---------------------------------------------------------------------------
#
# ЧТО БЫЛО. Два словаря выше (``ROLE_PERMISSIONS`` и ``MODULE_PERMISSIONS``)
# ведут роли под именами, которых в продукте НЕТ (``hse_specialist``,
# ``hse_head``, ``fire_engineer``, ``instructor``, ``methodist``,
# ``project_manager``), а настоящих ролей в них не хватает: семи в первом и
# девяти во втором. Для них набор прав выходил ПУСТЫМ, а ``PolicyEngine.can``
# спрашивает оба — сперва модуль, потом право. Токен доступа прав в себе не
# несёт (в нём ``tenant_id``, ``roles`` и ``company_id``), так что подставить их
# было неоткуда.
#
# Чем это оборачивалось (замер среза-226, живая проба): ``GET /briefings/...``
# отвечал 403 специалисту по охране труда, руководителю службы ОТиПБ и
# кадровику, хотя пункт меню «Инструктажи» виден десяти ролям. Тем же рубежом
# закрыты задания генерации, корпоративные риски и обучение.
#
# РЕШЕНИЕ. Список ролей у права живёт ОДИН РАЗ — в ``core/screen_access``
# (срез-217). Здесь заведён МОСТ: ресурс модуля → право экрана, по которому его
# читают и меняют. Права роли = то, что записано руками, ПЛЮС выведенное из
# карты. Именно объединение, а не замена: так никто не теряет доступ, который
# у него был, и правка монотонна — отказов становится только меньше.
#
# Мост намеренно ЯВНЫЙ: у каждой строки видно, каким экраном оправдан доступ к
# ресурсу. Ресурс без строки — ошибка на импорте, а не тихо пустые права.

#: Ресурс → (право экрана на ЧТЕНИЕ, право экрана на ИЗМЕНЕНИЕ).
_SCREEN_OF_RESOURCE: dict[str, tuple[str, str]] = {
    # Настройки платформы: только владелец и администратор (право пустое).
    "admin": ("admin.manage_roles", "admin.manage_roles"),
    "briefings": ("training.view", "training.assign"),
    "calendar": ("calendar.view", "calendar.view"),
    "contractors": ("contractor.view", "contractor.manage"),
    "data_quality": ("data_quality.view", "data_quality.view"),
    "document_jobs": ("generation.view", "generation.manage"),
    "document_versions": ("doc.view", "doc.create"),
    "documents": ("doc.view", "doc.create"),
    "employee_card": ("employee_card.view", "employee_card.view"),
    "files": ("file.view", "doc.create"),
    "incidents": ("incident.view", "incident.create"),
    "inspections": ("inspection.view", "inspection.create"),
    "package_presets": ("pack.view", "pack.manage"),
    "package_profiles": ("pack.view", "pack.manage"),
    "ppe_issues": ("ppe.view", "ppe.issue"),
    "ppe_norms": ("ppe.view", "ppe.issue"),
    "reports": ("reports.view", "reports.manage"),
    "risk_maps": ("risk.view", "risk.edit"),
    "risk_methodologies": ("risk.view", "risk.edit"),
    "template_versions": ("template.view", "template.edit"),
    "templates": ("template.view", "template.edit"),
    "trainings": ("training.view", "training.assign"),
    "warehouse_stock": ("warehouse.view", "ppe.issue"),
}

#: Точечные исключения: действие, которое стоит за ОТДЕЛЬНЫМ правом экрана.
_SCREEN_OF_ACTION: dict[tuple[str, str], str] = {
    ("documents", "sign"): "doc.sign",
    ("documents", "approve"): "doc.sign",
    ("documents", "send_edo"): "doc.sign",
    ("documents", "export"): "doc.export",
    ("documents", "download"): "doc.export",
    ("documents", "run_pipeline"): "generation.manage",
    ("document_versions", "download"): "doc.export",
    ("files", "sign"): "doc.sign",
    ("files", "download"): "doc.export",
    ("reports", "export"): "doc.export",
    ("reports", "download"): "doc.export",
    ("templates", "approve"): "template.activate",
    ("templates", "delete"): "template.delete",
    ("template_versions", "approve"): "template.activate",
    ("template_versions", "delete"): "template.delete",
    ("trainings", "approve"): "training.complete",
    ("incidents", "export"): "risk.export",
    ("inspections", "export"): "risk.export",
    ("risk_maps", "export"): "risk.export",
}

#: Действия, считающиеся изменением. Остальные — чтение.
_WRITE_ACTIONS: frozenset[str] = frozenset(
    {
        "create",
        "update",
        "delete",
        "approve",
        "sign",
        "send_edo",
        "run_pipeline",
        "retry_job",
        "cancel_job",
    }
)

#: Словарь кодов прав целиком — то, чем вообще оперирует движок.
ALL_PERMISSION_CODES: frozenset[str] = frozenset(
    code for codes in ROLE_PERMISSIONS.values() for code in codes
)


def screen_permission_for(resource: str, action: str) -> str:
    """Право экрана, которым оправдан доступ к ресурсу модуля."""

    override = _SCREEN_OF_ACTION.get((resource, action))
    if override:
        return override
    if resource not in _SCREEN_OF_RESOURCE:
        raise KeyError(f"ресурс «{resource}» не сопоставлен праву экрана")
    read_code, write_code = _SCREEN_OF_RESOURCE[resource]
    return write_code if action in _WRITE_ACTIONS else read_code


@functools.lru_cache(maxsize=64)
def _derived_permissions(role: str) -> frozenset[str]:
    """Права роли, выведенные из карты прав экрана.

    Результат кэшируется: зовётся на КАЖДОМ запросе, а зависит только от
    имени роли — обе карты статичны и живут в коде.
    """

    from app.core.screen_access import screen_roles  # noqa: PLC0415 — круг импортов

    granted: set[str] = set()
    for code in ALL_PERMISSION_CODES:
        resource, _, action = code.partition(":")
        if not action:
            continue
        if role in screen_roles(screen_permission_for(resource, action)):
            granted.add(code)
    return frozenset(granted)


def permissions_for_role(role: str) -> frozenset[str]:
    """Права роли: записанные руками ПЛЮС выведенные из карты прав экрана."""

    normalized = _normalize_role(role)
    return frozenset(ROLE_PERMISSIONS.get(normalized, set())) | _derived_permissions(normalized)


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    """То же для набора ролей человека."""

    granted: set[str] = set()
    for role in roles:
        granted |= permissions_for_role(str(role))
    return frozenset(granted)


def modules_for_role(role: str) -> frozenset[str]:
    """Модули, открытые роли: записанные руками ПЛЮС следующие из её прав."""

    normalized = _normalize_role(role)
    allowed = set(MODULE_PERMISSIONS.get(normalized, set()))
    for code in permissions_for_role(normalized):
        module = PolicyEngine._RESOURCE_TO_MODULE.get(code.partition(":")[0])
        if module:
            allowed.add(module)
    return frozenset(allowed)


def _check_roles_are_real() -> None:
    """Словари и синонимы не смеют называть роль, которой в продукте нет.

    СРЕЗ-228, проверка на импорте. Именно так словари и разошлись с жизнью: в
    них годами жили ``hse_specialist``, ``fire_engineer`` и ``instructor``, а
    настоящие роли не получали ничего — набор прав выходил ПУСТЫМ, и отказ
    приходил тому, кто работу и делает.
    """

    from app.models.tenant_billing import RoleEnum  # noqa: PLC0415 — круг импортов

    known = {role.value for role in RoleEnum}
    for name, table in (
        ("ROLE_PERMISSIONS", ROLE_PERMISSIONS),
        ("MODULE_PERMISSIONS", MODULE_PERMISSIONS),
    ):
        unknown = sorted(set(table) - known)
        if unknown:
            raise RuntimeError(f"{name} называет несуществующие роли: {unknown}")
    broken = sorted(target for target in ROLE_ALIASES.values() if target not in known)
    if broken:
        raise RuntimeError(f"ROLE_ALIASES ведут на несуществующие роли: {broken}")


_check_roles_are_real()


def _check_bridge() -> None:
    """Каждый ресурс словаря обязан быть сопоставлен праву экрана.

    Проверка на импорте, а не в тесте: неизвестный ресурс — это тихо пустые
    права, ровно та ловушка, что разбиралась в срезах 224 и 226.
    """

    resources = {code.partition(":")[0] for code in ALL_PERMISSION_CODES}
    missing = sorted(resources - set(_SCREEN_OF_RESOURCE))
    if missing:
        raise RuntimeError(f"ресурсы без права экрана: {missing}")


_check_bridge()


class PolicyEngine:
    _ACTION_ALIASES = {
        "generate": "run_pipeline",
        "run": "run_pipeline",
        "cancel": "cancel_job",
    }

    _RESOURCE_TO_MODULE: dict[str, str] = {
        "templates": "templates",
        "template_versions": "templates",
        "documents": "documents",
        "document_versions": "documents",
        "document_jobs": "documents",
        "files": "documents",
        "package_presets": "documents",
        "package_profiles": "documents",
        "risk_maps": "risk",
        "risk_methodologies": "risk",
        "ppe_norms": "ppe",
        "ppe_issues": "ppe",
        "warehouse_stock": "ppe",
        "trainings": "training",
        "briefings": "briefings",
        "incidents": "incidents",
        "inspections": "inspections",
        "contractors": "contractors",
        "reports": "reports",
        "admin": "admin",
    }

    def enforce(
        self,
        actor: ActorContext,
        action: str,
        resource: str,
        obj: Any | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        """Unified policy entrypoint required by business guards."""

        return self.can(actor=actor, action=action, resource=resource, obj=obj, ctx=ctx)

    def can(
        self,
        actor: ActorContext,
        action: str,
        resource: str,
        obj: Any | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        normalized_action = self._ACTION_ALIASES.get(action.lower(), action.lower())
        normalized_resource = resource.lower()
        permission_code = f"{normalized_resource}:{normalized_action}"
        ctx = ctx or {}

        # Cross-tenant isolation: a tenant-scoped ctx must match the actor's
        # tenant — even for owner/admin. Defense-in-depth alongside the request
        # middleware, so a forged/mismatched tenant scope can never be granted.
        ctx_tenant = ctx.get("tenant_id")
        if ctx_tenant and actor.tenant_id and str(ctx_tenant) != str(actor.tenant_id):
            return Decision(
                False,
                "cross_tenant_denied",
                audit_meta={"actor_tenant": str(actor.tenant_id), "ctx_tenant": str(ctx_tenant)},
            )

        # Check module-level access first
        module = self._RESOURCE_TO_MODULE.get(normalized_resource)
        if module:
            allowed_modules: set[str] = set()
            for role in actor.roles:
                # Срез-227: модули роли — из единой карты прав экрана тоже,
                # иначе настоящие роли не проходили даже сюда.
                allowed_modules.update(modules_for_role(role))
            if module not in allowed_modules:
                return Decision(
                    False,
                    "module_access_denied",
                    audit_meta={"module": module, "resource": normalized_resource},
                )

        # Owner/admin are super-users: once module + tenant checks pass they
        # bypass the resource-permission table (which may be intentionally
        # incomplete). Must precede the matched_roles gate so a missing
        # ROLE_PERMISSIONS entry never denies an owner/admin.
        if {"owner", "admin"}.intersection(actor.roles):
            return Decision(
                True,
                "explicit_allow",
                matched_rules=("rbac", "admin_bypass"),
            )

        matched_roles = tuple(
            # Срез-227: права роли — записанные руками ПЛЮС выведенные из
            # карты прав экрана (``permissions_for_role``).
            role
            for role in actor.roles
            if permission_code in permissions_for_role(role)
        )
        if not matched_roles:
            return Decision(False, "missing_permission", audit_meta={"permission": permission_code})

        if "auditor_ro" in actor.roles and normalized_action not in {"read", "list"}:
            return Decision(False, "auditor_read_only", matched_roles=matched_roles)

        if not self._scope_check(actor=actor, obj=obj, ctx=ctx):
            return Decision(
                False, "scope_mismatch", matched_roles=matched_roles, matched_rules=("scope_check",)
            )

        return Decision(
            True, "explicit_allow", matched_roles=matched_roles, matched_rules=("rbac", "abac")
        )

    def authorize(
        self,
        actor: ActorContext,
        action: str,
        resource: str,
        obj: Any | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        return self.can(actor=actor, action=action, resource=resource, obj=obj, ctx=ctx)

    @staticmethod
    def _scope_check(*, actor: ActorContext, obj: Any | None, ctx: dict[str, Any]) -> bool:
        attrs: dict[str, Any] = dict(ctx)
        if obj is not None:
            for name in (
                "company_id",
                "site_id",
                "project_id",
                "contractor_id",
                "document_id",
                "status",
                "risk_level",
            ):
                if hasattr(obj, name):
                    attrs.setdefault(name, getattr(obj, name))

        checks = (
            ("company_id", actor.company_ids),
            ("site_id", actor.site_ids),
            ("project_id", actor.project_ids),
            ("contractor_id", actor.contractor_ids),
        )
        for key, allowed_values in checks:
            value = attrs.get(key)
            if value and allowed_values and str(value) not in set(map(str, allowed_values)):
                return False

        status_value = attrs.get("status")
        if (
            status_value
            and actor.allowed_statuses
            and str(status_value) not in set(actor.allowed_statuses)
        ):
            return False

        risk_level = _normalize_risk_level(attrs.get("risk_level"))
        if (
            risk_level is not None
            and actor.max_risk_level is not None
            and risk_level > actor.max_risk_level
        ):
            return False

        return True


policy_engine = PolicyEngine()


def policy_forbidden(reason: str, *, correlation_id: str | None = None) -> HTTPException:
    _ = correlation_id
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(
            code="FORBIDDEN",
            message="Forbidden",
            error_type="policy",
            details={"reason_code": reason},
        ),
    )


def apply_abac_filters(query: Select[Any], actor: ActorContext, model: type[Any]) -> Select[Any]:
    return scoped_query(query, model=model, actor=actor, resource=model.__tablename__)


def scoped_query(
    query: Select[Any], *, model: type[Any], actor: ActorContext, resource: str | None = None
) -> Select[Any]:
    filters = []
    scoped_fields = 0
    normalized_resource = (resource or getattr(model, "__tablename__", "") or "").lower()

    if hasattr(model, "company_id"):
        scoped_fields += 1
        if actor.company_ids:
            filters.append(model.company_id.in_(actor.company_ids))
    elif normalized_resource in {"company", "companies"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.company_ids:
            filters.append(model.id.in_(actor.company_ids))
    if hasattr(model, "site_id"):
        scoped_fields += 1
        if actor.site_ids:
            filters.append(model.site_id.in_(actor.site_ids))
    elif normalized_resource in {"site", "sites"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.site_ids:
            filters.append(model.id.in_(actor.site_ids))
    if hasattr(model, "project_id"):
        scoped_fields += 1
        if actor.project_ids:
            filters.append(model.project_id.in_(actor.project_ids))
    elif normalized_resource in {"project", "projects"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.project_ids:
            filters.append(model.id.in_(actor.project_ids))
    if hasattr(model, "contractor_id"):
        scoped_fields += 1
        if actor.contractor_ids:
            filters.append(model.contractor_id.in_(actor.contractor_ids))
    elif normalized_resource in {"contractor", "contractors"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.contractor_ids:
            filters.append(model.id.in_(actor.contractor_ids))
    if hasattr(model, "status") and actor.allowed_statuses:
        filters.append(model.status.in_(actor.allowed_statuses))
    if hasattr(model, "risk_level") and actor.max_risk_level is not None:
        filters.append(model.risk_level <= actor.max_risk_level)
    if hasattr(model, "deleted_at"):
        filters.append(model.deleted_at.is_(None))
    if filters:
        query = query.where(and_(*filters))

    if (
        scoped_fields == 0
        and normalized_resource in SCOPED_RESOURCES
        and any((actor.company_ids, actor.site_ids, actor.project_ids, actor.contractor_ids))
    ):
        raise policy_forbidden("scoped_resource_without_scope_fields")
    return query


async def audit_authz_decision(
    *,
    session: AsyncSession,
    request: Request,
    actor: ActorContext,
    resource: str,
    action: str,
    decision: Decision,
    object_id: str | None = None,
) -> None:
    tenant = str(
        session.info.get("tenant_id")
        or session.info.get("token_tenant_id")
        or actor.tenant_id
        or ""
    ).strip()
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=tenant,
        action="authz_decision",
        object_type=resource,
        object_id=object_id or "-",
        user_id=actor.user_id,
        ip=request.client.host if request.client else "unknown",
        details={
            "event_type": "authz_decision",
            "resource": resource,
            "decision_action": action,
            "path": request.url.path,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "matched_roles": list(decision.matched_roles),
            "matched_rules": list(decision.matched_rules),
            "scopes": {
                "company_ids": list(actor.company_ids),
                "site_ids": list(actor.site_ids),
                "project_ids": list(actor.project_ids),
                "contractor_ids": list(actor.contractor_ids),
                "allowed_statuses": list(actor.allowed_statuses),
                "max_risk_level": actor.max_risk_level,
            },
        },
    )
