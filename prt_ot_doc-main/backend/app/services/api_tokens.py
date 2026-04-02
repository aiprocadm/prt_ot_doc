from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from app.models.models import ApiToken


class ApiTokenService:
    PREFIX = "ptd_"

    @classmethod
    def generate_raw_token(cls) -> str:
        return f"{cls.PREFIX}{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def issue_token(
        cls,
        *,
        tenant_id: str,
        name: str,
        scopes: list[str],
        created_by_user_id: str | None,
        expires_at: datetime | None,
    ) -> tuple[str, ApiToken]:
        raw_token = cls.generate_raw_token()
        token = ApiToken(
            tenant_id=tenant_id,
            name=name,
            token_hash=cls.hash_token(raw_token),
            scopes_json=scopes,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            is_revoked=False,
        )
        return raw_token, token

    @classmethod
    def verify_hash(cls, raw_token: str, token_hash: str) -> bool:
        return secrets.compare_digest(cls.hash_token(raw_token), token_hash)

    @staticmethod
    def is_expired(token: ApiToken) -> bool:
        return bool(token.expires_at and token.expires_at <= datetime.now(timezone.utc))
