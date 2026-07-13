"""RBAC guard for the notifications router (route-group sweep).

The only role gap in ``backend/app/api/routes/notifications.py`` was
``POST /notifications/templates`` (``upsert_template``): tenant-wide template
config that shipped with a no-op ``Depends(rbac())`` (auth-only, no role gate),
so any authenticated tenant user — including a rank-and-file ``worker`` — could
overwrite notification templates. Contract: worker → 403, owner/admin → allowed.

The per-user notification GET/mark-read/settings endpoints are intentionally
auth-only (a user reads/acks their own notifications) and are NOT role-guarded,
so they are not asserted here.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_TEMPLATE_BODY = {
    "code": "sweep-template",
    "channel": "email",
    "type": "JobStatusChanged",  # must be a valid NotificationType enum value
    "body_template": "Hello {{name}}",
}


@pytest.mark.anyio
async def test_notification_template_write_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/notifications/templates", json=_TEMPLATE_BODY, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_notification_template_write_forbidden_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    """Tenant-wide template config is admin/owner-only; ot_specialist is excluded."""
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/notifications/templates", json=_TEMPLATE_BODY, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_notification_template_write_allowed_for_admin(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        "/api/v1/notifications/templates", json=_TEMPLATE_BODY, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["code"] == _TEMPLATE_BODY["code"]
