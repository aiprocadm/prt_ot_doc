"""Identity & authorization ORM models (users, sessions, RBAC/ABAC) — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py.

This block binds ``RoleEnum`` at RUNTIME (native_enum(RoleEnum)) and AuthzBaseModel subclasses the declarative ``TenantBase``; both are imported normally (not under TYPE_CHECKING).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import TenantBase
from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
    TimestampMixin,
    UUIDMixin,
    VersionedMixin,
    native_enum,
)
from app.models.tenant_billing import RoleEnum

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Company,
        User,
    )


class User(TenantBaseModel, SoftDeleteMixin):
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(native_enum(RoleEnum), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped[Company | None] = relationship("Company", backref="users", lazy="joined")
    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_user_email", "tenant_id", "email", unique=True),
        Index("ix_user_company", "tenant_id", "company_id"),
    )


class RefreshSession(TenantBaseModel):
    __tablename__ = "refresh_session"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    parent_token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replaced_by_token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_refresh_session_user_family", "tenant_id", "user_id", "family_id"),
        Index("ix_refresh_session_family_active", "tenant_id", "family_id", "revoked_at"),
    )


class UserRole(TenantBaseModel):
    __tablename__ = "user_role"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[RoleEnum] = mapped_column(native_enum(RoleEnum), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "role", name="uq_user_role"),
        Index("ix_user_role_user", "tenant_id", "user_id"),
    )


class UserAttribute(TenantBaseModel):
    __tablename__ = "user_attribute"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    site_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    project_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    contractor_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_user_attribute"),
        Index("ix_user_attribute_user", "tenant_id", "user_id"),
    )


class AuthzBaseModel(TenantBase, TimestampMixin, VersionedMixin, UUIDMixin):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )


class AuthzRole(AuthzBaseModel):
    __tablename__ = "authz_roles"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_authz_roles_tenant_code"),)


class AuthzPermission(AuthzBaseModel):
    __tablename__ = "authz_permissions"

    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_authz_permission_resource_action"),
    )


class AuthzRolePermission(AuthzBaseModel):
    __tablename__ = "authz_role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authz_roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("authz_permissions.id", ondelete="CASCADE"), nullable=True
    )
    permission_code: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_code",
            name="uq_authz_role_permissions_tenant_role_code",
        ),
    )


class AuthzUserRole(AuthzBaseModel):
    __tablename__ = "authz_user_roles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authz_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "role_id", name="uq_authz_user_roles_tenant_user_role"
        ),
        Index("ix_authz_user_roles_user", "tenant_id", "user_id"),
        Index("ix_authz_user_roles_role", "tenant_id", "role_id"),
    )


class AuthzPolicy(AuthzBaseModel):
    __tablename__ = "authz_policies"

    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    effect: Mapped[str] = mapped_column(String(8), nullable=False)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_authz_policy_lookup", "tenant_id", "resource", "action", "enabled", "priority"),
    )


class ApiKey(TenantBaseModel):
    __tablename__ = "api_key"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="api:read")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_api_key_tenant_name"),)

    @property
    def scope_list(self) -> list[str]:
        return [scope for scope in self.scopes.split() if scope]
