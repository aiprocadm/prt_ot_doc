"""Security primitives for unified authorization enforcement.

This package exposes the new policy-enforcement primitives while keeping a
compatibility surface for existing route modules that still import the legacy
RBAC/ABAC symbols from ``app.core.security``.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

from .context import UserContext
from .enforce import enforce

_legacy_path = Path(__file__).resolve().parent.parent / "security.py"
_legacy_spec = spec_from_file_location("app.core._legacy_security", _legacy_path)
if _legacy_spec is None or _legacy_spec.loader is None:  # pragma: no cover - defensive
    raise RuntimeError(f"Unable to load legacy security module: {_legacy_path}")

_legacy_security = module_from_spec(_legacy_spec)
sys.modules[_legacy_spec.name] = _legacy_security
_legacy_spec.loader.exec_module(_legacy_security)

AccessContext = _legacy_security.AccessContext
AuthContext = _legacy_security.AuthContext
abac = _legacy_security.abac
api_key_auth = _legacy_security.api_key_auth
decode_token = _legacy_security.decode_token
get_auth_ctx = _legacy_security.get_auth_ctx
issue_access_token = _legacy_security.issue_access_token
issue_refresh_token = _legacy_security.issue_refresh_token
rbac = _legacy_security.rbac
verify_token = _legacy_security.verify_token

__all__ = [
    "UserContext",
    "enforce",
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
