"""BIZ-49 срез-10: срок жизни контекста и запреты имперсонации (Доп. №3, 63.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.managed_clients.impersonation import (
    CONTEXT_TTL,
    FORBIDDEN_IN_CONTEXT,
    ForbiddenInContext,
    ImpersonationExpired,
    ensure_action_allowed,
    ensure_session_active,
    session_expires_at,
    session_seconds_left,
)

_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def test_context_lives_an_hour_not_forever() -> None:
    """ТЗ: «сессия имперсонации истекает (напр. 60 мин), не навсегда»."""

    assert CONTEXT_TTL == timedelta(minutes=60)
    assert session_expires_at(_NOW) == _NOW + timedelta(minutes=60)


def test_fresh_session_is_active() -> None:
    ensure_session_active(started_at=_NOW, ended_at=None, now=_NOW + timedelta(minutes=59))


def test_expired_session_is_refused() -> None:
    with pytest.raises(ImpersonationExpired):
        ensure_session_active(started_at=_NOW, ended_at=None, now=_NOW + timedelta(minutes=61))


def test_session_closed_by_hand_is_refused() -> None:
    """Выход из контекста — не только «баннер пропал», но и отказ на сервере."""

    with pytest.raises(ImpersonationExpired):
        ensure_session_active(
            started_at=_NOW,
            ended_at=_NOW + timedelta(minutes=5),
            now=_NOW + timedelta(minutes=6),
        )


def test_naive_timestamps_from_sqlite_do_not_crash() -> None:
    """SQLite отдаёт время без часового пояса — сравнение с aware упало бы."""

    ensure_session_active(
        started_at=_NOW.replace(tzinfo=None), ended_at=None, now=_NOW + timedelta(minutes=1)
    )


def test_seconds_left_never_goes_negative() -> None:
    assert session_seconds_left(started_at=_NOW, now=_NOW + timedelta(minutes=10)) == 3000
    assert session_seconds_left(started_at=_NOW, now=_NOW + timedelta(hours=5)) == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/auth/change-password"),
        ("POST", "/api/v1/auth/2fa/enable"),
        ("DELETE", "/api/v1/persons/abc"),
        ("GET", "/api/v1/privacy/export"),
        ("POST", "/api/v1/billing/payment-methods"),
        ("POST", "/api/v1/api-tokens"),
        ("PATCH", "/api/v1/admin/authz/roles/1"),
    ],
)
def test_dangerous_actions_are_refused_in_context(method: str, path: str) -> None:
    """Доп. №3 63.2: пароли/2FA, платёжные данные, массовый экспорт ПДн,
    удаление данных и настройки безопасности запрещены даже в контексте."""

    with pytest.raises(ForbiddenInContext):
        ensure_action_allowed(method=method, path=path)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/persons"),
        ("POST", "/api/v1/persons"),
        ("PATCH", "/api/v1/persons/abc"),
        ("GET", "/api/v1/medical/exams"),
        # Выход из контекста обязан работать: иначе запрет запирает сам себя.
        ("DELETE", "/api/v1/managed-clients/context"),
        # Вход в систему — POST, и он не «действие в данных клиента».
        ("POST", "/api/v1/auth/login"),
    ],
)
def test_ordinary_work_is_untouched(method: str, path: str) -> None:
    ensure_action_allowed(method=method, path=path)


def test_every_forbidden_rule_explains_itself() -> None:
    """Отказ без причины читается как поломка и порождает обращение в поддержку."""

    assert FORBIDDEN_IN_CONTEXT
    for rule in FORBIDDEN_IN_CONTEXT:
        assert rule.reason.strip()
        assert rule.prefixes
