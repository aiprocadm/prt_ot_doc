"""Password hashing helpers."""

from __future__ import annotations

from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str, *, pepper: str | None = None) -> str:
    """Hash a password using Argon2 with an optional pepper."""

    if pepper:
        password = f"{password}{pepper}"
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str, *, pepper: str | None = None) -> bool:
    """Verify a password against an Argon2 hash."""

    if pepper:
        password = f"{password}{pepper}"
    try:
        return pwd_context.verify(password, hashed)
    except ValueError:  # pragma: no cover - invalid hashes rejected
        return False


__all__ = [
    "hash_password",
    "verify_password",
]
