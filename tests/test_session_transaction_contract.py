"""Services and dependencies must not own the request transaction.

``transaction_scope`` (``app.db.session``) commits once at the end of a request. A
``commit()`` anywhere inside a service or a FastAPI dependency ends that transaction
early, which drops the transaction-local SEC-65 GUCs (``app.current_tenant`` /
``app.bypass_rls``) for everything that runs afterwards — under FORCE ROW LEVEL SECURITY
the rest of the handler then reads zero rows and its writes are rejected.

``api_key_auth`` is the sharpest case: it is a dependency, so its commit landed *before*
the handler body and silently emptied every list endpoint under ``/api/v1/public``. These
tests pin the contract for the paths that regressed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend" / "app"

# (module, function) pairs that must never call session.commit() themselves.
NO_COMMIT_FUNCTIONS = [
    ("services/api_keys.py", "create_api_key"),
    ("services/api_keys.py", "authenticate_api_key"),
    ("services/api_keys.py", "rotate_api_key"),
]


def _function_node(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path}: function {name} not found")


def _commit_calls(node: ast.AST) -> list[int]:
    """Line numbers of ``<something>.commit()`` calls inside ``node``."""

    return [
        child.lineno
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "commit"
    ]


@pytest.mark.parametrize(("module", "func"), NO_COMMIT_FUNCTIONS)
def test_service_does_not_own_the_transaction(module: str, func: str) -> None:
    path = BACKEND / module
    lines = _commit_calls(_function_node(path, func))
    assert not lines, (
        f"{module}::{func} calls commit() at line(s) {lines}. "
        "Use flush(): transaction_scope owns the request transaction, and an early commit "
        "drops the transaction-local RLS GUCs (SEC-65) for the rest of the request."
    )


def test_login_does_not_commit_before_creating_the_refresh_session() -> None:
    """The refresh-session INSERT must land in the same transaction as its GUCs."""

    path = BACKEND / "api/routes/auth.py"
    node = _function_node(path, "login")
    commits = _commit_calls(node)
    create_calls = [
        child.lineno
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "create_refresh_session"
    ]
    assert create_calls, "login() no longer creates a refresh session — update this test"
    assert commits, "login() must still commit once at the end"
    assert min(commits) > max(create_calls), (
        f"login() commits at line {min(commits)} before create_refresh_session at "
        f"{max(create_calls)}. The commit ends the transaction and clears app.current_tenant, "
        "so the refresh_session INSERT would be evaluated without a tenant context."
    )
