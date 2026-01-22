"""JWT issuance, verification, and role-based access control utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.tenant import set_current_tenant
from app.core.config import Settings, get_settings
from app.models.models import ApiKey, User
from app.services.api_keys import authenticate_api_key

__all__ = [
    "issue_access_token",
    "issue_refresh_token",
    "decode_token",
    "verify_token",
    "AccessContext",
    "AuthContext",
    "get_auth_ctx",
    "rbac",
    "abac",
    "api_key_auth",
]


_bearer_scheme = HTTPBearer(auto_error=False)


def _auth_error(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _api_key_error(detail: str = "Invalid API key") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "ApiKey"},
    )


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _base_payload(
    subject: str,
    *,
    expires_at: datetime,
    token_type: str,
    settings: Settings,
    additional_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issued_at = _now()
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": subject,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid4()),
        "type": token_type,
    }
    if additional_claims:
        payload.update(additional_claims)
    return payload


def issue_access_token(
    *,
    subject: str,
    tenant: str,
    role: str,
    settings: Settings | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a short-lived access token for the given subject."""

    settings = settings or get_settings()
    expires_at = _now() + timedelta(minutes=settings.jwt_access_ttl_minutes)
    subject_str = str(subject)
    claims = {"tenant": str(tenant), "role": str(role)}
    if additional_claims:
        claims.update(additional_claims)
    payload = _base_payload(
        subject_str,
        expires_at=expires_at,
        token_type="access",
        settings=settings,
        additional_claims=claims,
    )
    return jwt.encode(payload, settings.jwt_private_key_pem, algorithm=settings.jwt_algorithm)


def issue_refresh_token(
    *,
    subject: str,
    tenant: str,
    role: str,
    settings: Settings | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a long-lived refresh token for the given subject."""

    settings = settings or get_settings()
    expires_at = _now() + timedelta(days=settings.jwt_refresh_ttl_days)
    subject_str = str(subject)
    claims = {"tenant": str(tenant), "role": str(role)}
    if additional_claims:
        claims.update(additional_claims)
    payload = _base_payload(
        subject_str,
        expires_at=expires_at,
        token_type="refresh",
        settings=settings,
        additional_claims=claims,
    )
    return jwt.encode(payload, settings.jwt_private_key_pem, algorithm=settings.jwt_algorithm)


def decode_token(
    token: str,
    *,
    settings: Settings | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decode a JWT and return its payload or raise an authentication error."""

    settings = settings or get_settings()
    default_options = {
        "verify_signature": True,
        "verify_aud": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_nbf": True,
        "verify_iss": True,
        "require_aud": True,
        "require_exp": True,
        "require_iat": True,
        "require_sub": True,
    }
    jwt_options = default_options if options is None else {**default_options, **options}
    try:
        return jwt.decode(
            token,
            settings.jwt_public_key_pem,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=jwt_options,
        )
    except JWTError as exc:  # pragma: no cover - jose provides detailed error types
        raise _auth_error() from exc


def verify_token(
    token: str,
    *,
    expected_type: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode the token and validate the expected token type."""

    payload = decode_token(token, settings=settings)
    if expected_type is not None and payload.get("type") != expected_type:
        raise _auth_error("Incorrect token type")
    return payload


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Authenticated user coupled with token claims for RBAC/ABAC checks."""

    user: User
    claims: Mapping[str, Any]
    tenant_slug: str | None
    tenant_id: UUID | None
    company_id: str | None

    def ensure_tenant_access(self, tenant_id: UUID | str | None, *, action: str = "write") -> None:
        """Ensure the JWT tenant matches the resource tenant."""

        if tenant_id is None:
            return

        if self.tenant_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Tenant mismatch for {action} operation",
            )

        if str(tenant_id) != str(self.tenant_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Tenant mismatch for {action} operation",
            )

    @property
    def role(self) -> str:
        return self.user.role.value

    def ensure_company_access(
        self, company_id: str | None, *, action: str = "access company resource"
    ) -> None:
        if company_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Company assignment required for {action}",
            )

        if self.company_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"User is not linked to a company for {action}",
            )

        if str(company_id) != str(self.company_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Company mismatch for {action}",
            )

    def to_auth_context(self) -> "AuthContext":
        """Convert the access context into a serializable auth context."""

        tenant_candidates: Iterable[Any] = (
            self.claims.get("tenant_id"),
            self.tenant_id,
            getattr(self.user, "tenant_id", None),
            self.claims.get("tenant"),
        )

        tenant_identifier: str | None = None
        for candidate in tenant_candidates:
            if candidate:
                tenant_identifier = str(candidate)
                break

        roles: list[str] = []
        claim_roles = self.claims.get("roles")
        if isinstance(claim_roles, Iterable) and not isinstance(claim_roles, (str, bytes)):
            roles.extend(str(role).lower() for role in claim_roles if role)

        single_role = self.claims.get("role")
        if isinstance(single_role, str) and single_role:
            roles.append(single_role.lower())

        normalized_role = str(self.role).lower()
        roles.append(normalized_role)

        deduplicated_roles = list(dict.fromkeys(roles))

        return AuthContext(
            sub=str(self.user.id),
            tenant_id=tenant_identifier,
            roles=deduplicated_roles,
            company_id=self.company_id,
        )


class AuthContext(BaseModel):
    """Lightweight authenticated subject representation for request handlers."""

    sub: str
    tenant_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    company_id: str | None = None

    model_config = ConfigDict(extra="ignore")

    def has_role(self, role: str) -> bool:
        normalized = {value.lower() for value in self.roles}
        return role.lower() in normalized


def get_auth_ctx(request: Request) -> AuthContext:
    """Return an auth context stored on the request state or raise 401."""

    access_context = getattr(request.state, "access_context", None)
    if isinstance(access_context, AccessContext):
        return access_context.to_auth_context()

    raw_context = getattr(request.state, "auth", None)
    if raw_context is None:
        raise _auth_error()

    if isinstance(raw_context, AuthContext):
        return raw_context

    if isinstance(raw_context, Mapping):
        try:
            return AuthContext.model_validate(raw_context)
        except ValidationError as exc:  # pragma: no cover - validation bubble-up
            raise _auth_error() from exc

    raise _auth_error()


def _normalize_roles(required_roles: Sequence[str] | None) -> frozenset[str]:
    return frozenset({role.lower() for role in (required_roles or []) if role})


def rbac(required_roles: list[str] | None = None) -> Callable[..., Any]:
    """Return a dependency that enforces role- and tenant-based access control."""

    normalized_roles = _normalize_roles(required_roles)

    async def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
        session: AsyncSession = Depends(get_session),
    ) -> AccessContext:
        if credentials is None:
            raise _auth_error()

        payload = verify_token(credentials.credentials, expected_type="access")
        subject = payload.get("sub")
        if subject is None:
            raise _auth_error()

        token_role = str(payload.get("role") or "").lower()
        token_tenant_slug = str(payload.get("tenant") or "").strip() or None
        session_tenant = str(session.info.get("tenant") or "").strip()

        if token_tenant_slug and session_tenant and token_tenant_slug != session_tenant:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Tenant scope mismatch",
            )

        result = await session.execute(select(User).where(User.id == subject))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise _auth_error()

        raw_tenant_id = payload.get("tenant_id")
        token_tenant_id: UUID | None
        if raw_tenant_id in (None, ""):
            token_tenant_id = None
        else:
            try:
                token_tenant_id = UUID(str(raw_tenant_id))
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Invalid tenant identifier in token",
                ) from exc

        if token_tenant_id is not None and str(user.tenant_id) != str(token_tenant_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Tenant assignment mismatch",
            )

        token_company_id = payload.get("company_id")
        if token_company_id:
            normalized_token_company = str(token_company_id)
            user_company = str(user.company_id) if getattr(user, "company_id", None) else None
            if user_company is None or normalized_token_company != user_company:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Company assignment mismatch",
                )

        if normalized_roles and token_role not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )

        session.info["current_user_id"] = user.id
        session.info["current_user_role"] = user.role.value
        session.info["token_payload"] = dict(payload)
        session.info["token_tenant_id"] = str(token_tenant_id) if token_tenant_id else None
        session.info["token_tenant_slug"] = token_tenant_slug
        session.info["current_user_company_id"] = (
            str(user.company_id) if getattr(user, "company_id", None) else None
        )

        request.state.current_user = user
        request.state.current_user_id = user.id
        request.state.current_user_company_id = session.info["current_user_company_id"]
        request.state.rate_limit_subject = user.id

        access_context = AccessContext(
            user=user,
            claims=MappingProxyType(dict(payload)),
            tenant_slug=token_tenant_slug,
            tenant_id=token_tenant_id,
            company_id=(str(user.company_id) if getattr(user, "company_id", None) else None),
        )
        if token_tenant_slug:
            set_current_tenant(token_tenant_slug)
        request.state.access_context = access_context
        if token_tenant_id is not None:
            request.state.rate_limit_tenant_id = str(token_tenant_id)
        elif token_tenant_slug:
            request.state.rate_limit_tenant_id = token_tenant_slug

        return access_context

    return dependency


async def api_key_auth(
    request: Request,
    api_key_header: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    if not api_key_header:
        raise _api_key_error("Missing API key")

    record = await authenticate_api_key(session, api_key_header)
    if record is None:
        raise _api_key_error()

    request.state.api_key = record
    request.state.rate_limit_subject = f"api-key:{record.key_prefix}"
    request.state.rate_limit_tenant_id = str(record.tenant_id)

    auth_context = AuthContext(
        sub=f"api_key:{record.id}",
        tenant_id=str(record.tenant_id),
        roles=record.scope_list,
    )
    request.state.auth = auth_context

    return record


def abac(
    resource_tenant_id: Callable[..., UUID | str | None] | UUID | str | None,
    *,
    required_roles: list[str] | None = None,
    action: str = "access",
) -> Callable[..., Any]:
    """Return a dependency enforcing tenant-based ABAC checks for a resource."""

    base_access = Depends(rbac(required_roles))

    if callable(resource_tenant_id):
        tenant_dependency: Callable[..., UUID | str | None] = resource_tenant_id
    else:

        async def tenant_dependency() -> UUID | str | None:  # pragma: no cover - trivial
            return resource_tenant_id

    async def dependency(
        request: Request,
        tenant_id: UUID | str | None = Depends(tenant_dependency),
        access: AccessContext = base_access,
    ) -> AccessContext:
        access.ensure_tenant_access(tenant_id, action=action)
        if tenant_id is not None:
            request.state.rate_limit_tenant_id = str(tenant_id)
        return access

    return dependency
