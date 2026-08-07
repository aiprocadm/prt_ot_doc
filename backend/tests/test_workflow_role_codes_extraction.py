"""iter-28 RB-005 pin tests — `_extract_role_codes` helper in workflow/api.py.

Why these tests exist:

* The credential-smoke artifact `e2e-backend-log-bootstrap_local` from CI run
  [26444184689] showed every authenticated page rendering broken because
  `frontend/src/api/navigation.ts:11` polls ``/api/v1/workflow/tasks`` on every
  page load. The endpoint crashed with ``AttributeError: 'UserRole' object has
  no attribute 'code'`` and 500'd the response, breaking the sidebar/topbar
  render flow → Playwright timed out waiting for the "Документы" heading.
* Root cause: ``backend/app/modules/workflow/api.py`` had 5 sites accessing
  ``role.code`` on UserRole rows, but UserRole has only ``user_id`` /
  ``role: RoleEnum``. The correct attribute path is ``role.role.value`` (as in
  ``auth.py:413``, ``policy_engine.py:32``, ``security.py:517``,
  ``admin_users.py:62`` — four pre-existing call sites use it correctly).
* These tests pin the extraction shape against future regression: if anyone
  reverts to ``role.code`` or changes the relationship to be a list[RoleEnum]
  directly, these tests fail before CI hits an integration test.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.models.models import RoleEnum, UserRole
from app.modules.workflow.api import _extract_role_codes


def _make_user_role(role: RoleEnum) -> UserRole:
    """Construct an unattached UserRole row.

    We deliberately bypass ``session.add`` — the unit under test reads the
    Python attribute, not anything tied to a DB session, and avoiding the
    session keeps the test free of DB fixtures.
    """

    return UserRole(
        tenant_id="00000000-0000-0000-0000-000000000000",
        user_id="00000000-0000-0000-0000-000000000001",
        role=role,
    )


def _access_with_roles(*roles: RoleEnum) -> SimpleNamespace:
    """Mirror :class:`AccessContext` minimally: ``access.user.roles`` chain."""

    user = SimpleNamespace(roles=[_make_user_role(r) for r in roles])
    return SimpleNamespace(user=user)


def test_extract_role_codes_returns_string_values_for_each_userrole_row() -> None:
    access = _access_with_roles(RoleEnum.OWNER, RoleEnum.ADMIN)

    codes = _extract_role_codes(access)

    # Order preserved; .value lowercase strings (not Enum names).
    assert codes == ["owner", "admin"]
    assert all(isinstance(c, str) for c in codes)


def test_extract_role_codes_returns_empty_list_when_user_has_no_roles() -> None:
    user = SimpleNamespace(roles=[])
    access = SimpleNamespace(user=user)

    assert _extract_role_codes(access) == []


def test_extract_role_codes_tolerates_missing_roles_attribute() -> None:
    """``getattr(user, 'roles', None) or []`` must not raise if SQLAlchemy
    didn't materialise the relationship (e.g. unattached test User)."""

    user = SimpleNamespace()  # no `roles` attribute at all
    access = SimpleNamespace(user=user)

    assert _extract_role_codes(access) == []


def test_extract_role_codes_tolerates_none_roles() -> None:
    """selectinload misses can leave ``user.roles`` as ``None`` — must coalesce."""

    user = SimpleNamespace(roles=None)
    access = SimpleNamespace(user=user)

    assert _extract_role_codes(access) == []


def test_extract_role_codes_uses_role_role_value_not_role_code() -> None:
    """Regression guard: any future change that flips back to ``role.code``
    (which doesn't exist on UserRole) would raise AttributeError here, not
    silently in a 500 response captured only by Playwright."""

    access = _access_with_roles(RoleEnum.OT_PB_LEAD)

    # Must not raise. Returns the .value, NOT the enum NAME or .code.
    codes = _extract_role_codes(access)
    assert codes == ["ot_pb_lead"]
    assert "OT_PB_LEAD" not in codes  # not the enum NAME
    assert not hasattr(_make_user_role(RoleEnum.OWNER), "code"), (
        "UserRole must NOT acquire a .code attribute — if it does, this test's "
        "premise is wrong and the helper needs a redesign."
    )


def test_extract_role_codes_matches_workflowtask_assignee_role_code_format() -> None:
    """The string values returned must be comparable to
    :attr:`WorkflowTask.assignee_role_code` (a plain String column populated
    via :class:`RoleEnum` ``.value``). Pin the contract."""

    from app.modules.workflow.service import (
        WorkflowService,  # late import — avoids circular at module load
    )

    # Service uses role_codes for an SQL IN-clause filter against assignee_role_code.
    # No actual DB call here — we just sanity-check that the extracted code is a
    # plain string (not Enum) so the comparison works as expected.
    access = _access_with_roles(RoleEnum.HR)
    codes = _extract_role_codes(access)

    assert codes == ["hr"]
    assert WorkflowService is not None  # smoke: import path is stable
