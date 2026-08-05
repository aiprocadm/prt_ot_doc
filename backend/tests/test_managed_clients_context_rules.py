"""Unit: BIZ-49 срез-7 — правила работы «в контексте клиента» (разд. 49.3).

ТЗ: «Impersonation / работа в контексте клиента — с ОБЯЗАТЕЛЬНОЙ пометкой
в аудите: кто, от имени какого клиента, что сделал. Требование ПДн: действия
аутсорсера в данных клиента всегда трассируемы».

Здесь решается, когда контекст принимается, когда отвергается — и что именно
обязано попасть в след.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.managed_clients.access import AccessGrant
from app.domains.managed_clients.context import (
    ClientContext,
    ClientContextDenied,
    build_context_audit_meta,
    resolve_client_context,
)

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _grant(*, all_modules=True, modules=(), revoked_at=None) -> AccessGrant:
    return AccessGrant(
        client_id="mc1",
        user_id="u1",
        all_modules=all_modules,
        modules=tuple(modules),
        revoked_at=revoked_at,
    )


class TestResolve:
    def test_active_grant_gives_context(self):
        ctx = resolve_client_context(
            grant=_grant(), user_id="u1", client_id="mc1", client_name="Ромашка", now=_NOW
        )
        assert isinstance(ctx, ClientContext)
        assert ctx.client_id == "mc1"
        assert ctx.user_id == "u1"
        assert ctx.all_modules is True

    def test_missing_grant_is_denied(self):
        """Нет гранта — отказ, а не «работай в своём контексте»."""
        with pytest.raises(ClientContextDenied):
            resolve_client_context(
                grant=None, user_id="u1", client_id="mc1", client_name="Ромашка", now=_NOW
            )

    def test_revoked_grant_is_denied(self):
        with pytest.raises(ClientContextDenied):
            resolve_client_context(
                grant=_grant(revoked_at=_NOW - timedelta(days=1)),
                user_id="u1",
                client_id="mc1",
                client_name="Ромашка",
                now=_NOW,
            )

    def test_grant_of_another_user_is_denied(self):
        """Грант коллеги — не мой доступ, даже если клиент тот же."""
        other = AccessGrant(
            client_id="mc1", user_id="u2", all_modules=True, modules=(), revoked_at=None
        )
        with pytest.raises(ClientContextDenied):
            resolve_client_context(
                grant=other, user_id="u1", client_id="mc1", client_name="Ромашка", now=_NOW
            )

    def test_grant_for_another_client_is_denied(self):
        """Грант на другого клиента не пускает в этого — иначе доступ «переползает»."""
        other = AccessGrant(
            client_id="mc-other", user_id="u1", all_modules=True, modules=(), revoked_at=None
        )
        with pytest.raises(ClientContextDenied):
            resolve_client_context(
                grant=other, user_id="u1", client_id="mc1", client_name="Ромашка", now=_NOW
            )

    def test_module_scoped_context_keeps_the_list(self):
        ctx = resolve_client_context(
            grant=_grant(all_modules=False, modules=("documents",)),
            user_id="u1",
            client_id="mc1",
            client_name="Ромашка",
            now=_NOW,
        )
        assert ctx.all_modules is False
        assert ctx.modules == ("documents",)

    def test_context_allows_only_granted_module(self):
        ctx = resolve_client_context(
            grant=_grant(all_modules=False, modules=("documents",)),
            user_id="u1",
            client_id="mc1",
            client_name="Ромашка",
            now=_NOW,
        )
        assert ctx.allows("documents") is True
        assert ctx.allows("training") is False

    def test_all_modules_context_allows_anything(self):
        ctx = resolve_client_context(
            grant=_grant(), user_id="u1", client_id="mc1", client_name="Ромашка", now=_NOW
        )
        assert ctx.allows("training") is True


class TestAuditMeta:
    def test_meta_answers_who_on_behalf_of_whom_and_what(self):
        """ТЗ требует ровно три ответа: кто, от имени какого клиента, что сделал."""
        ctx = resolve_client_context(
            grant=_grant(), user_id="u1", client_id="mc1", client_name="Ромашка", now=_NOW
        )
        meta = build_context_audit_meta(ctx, action="documents.read")

        assert meta["actor_user_id"] == "u1"  # кто
        assert meta["managed_client_id"] == "mc1"  # от имени какого клиента
        assert meta["managed_client_name"] == "Ромашка"
        assert meta["action"] == "documents.read"  # что
        assert meta["on_behalf_of_client"] is True

    def test_meta_records_module_scope(self):
        ctx = resolve_client_context(
            grant=_grant(all_modules=False, modules=("documents", "training")),
            user_id="u1",
            client_id="mc1",
            client_name="Ромашка",
            now=_NOW,
        )
        meta = build_context_audit_meta(ctx, action="x")
        assert meta["all_modules"] is False
        assert sorted(meta["modules"]) == ["documents", "training"]

    def test_meta_is_json_safe(self):
        """Пометка уходит в JSON-поле аудита: никаких кортежей и объектов."""
        import json

        ctx = resolve_client_context(
            grant=_grant(all_modules=False, modules=("documents",)),
            user_id="u1",
            client_id="mc1",
            client_name="Ромашка",
            now=_NOW,
        )
        json.dumps(build_context_audit_meta(ctx, action="x"))
