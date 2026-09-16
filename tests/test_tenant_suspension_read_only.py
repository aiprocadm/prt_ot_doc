"""OPS-72, разд. 72.1: приостановка — «только чтение», а не запертая дверь.

ТЗ в карте жизненного цикла: «Приостановка | Неоплата / пауза → **safe
read-only, данные сохранены**», и сам ТЗ помечает эту строку «Частично».

ЧТО БЫЛО. Выключатель подписки означал ПОЛНУЮ блокировку (403 на любой запрос).
Клиент с просроченным счётом не мог ни посмотреть свои данные, ни выгрузить их,
ни войти. При этом для клиентов ПРИОСТАНОВЛЕННОГО ПАРТНЁРА режим чтения уже был
сделан — и там прямо записано, почему полная блокировка недопустима: «клиент не
может даже забрать свои данные». Для своей приостановки то же самое не чинили.

Здесь закрепляются РЕШЕНИЯ:

1. читать можно — иначе это не «только чтение», а отказ;
2. писать нельзя — иначе приостановка ничего не значит;
3. **вход работает**: он POST, и без исключения «только чтение» стало бы «нет
   доступа»;
4. **выгрузка и расторжение работают**: право забрать свои данные не зависит от
   оплаты следующего месяца (152-ФЗ, разд. 72.2);
5. отказ называет причину словами — «запрещено» без объяснения читается как
   поломка платформы.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.middleware.tenant_suspension import (
    TENANT_SUSPENDED_READ_ONLY,
    TenantSuspensionReadOnlyMiddleware,
)


class _Called(Exception):
    """Запрос пропущен дальше — то есть middleware не вмешался."""


async def _next(_request):
    raise _Called


def _request(method: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers={"x-tenant": "acme"},
        state=SimpleNamespace(),
    )


def _middleware(tenant_active: bool | None) -> TenantSuspensionReadOnlyMiddleware:
    middleware = TenantSuspensionReadOnlyMiddleware(app=None)  # type: ignore[arg-type]
    return middleware


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch):
    """Подменяем разбор арендатора: проверяем ПРАВИЛО, а не работу с базой."""

    def _install(tenant_active: bool | None) -> None:
        import app.middleware.tenant_suspension as module

        monkeypatch.setattr(module, "_resolve_tenant_slug", lambda _request: "acme")

        async def _resolve(_request, _identifier):
            if tenant_active is None:
                return None
            return SimpleNamespace(is_active=tenant_active, slug="acme")

        monkeypatch.setattr(module, "resolve_request_tenant", _resolve)

    return _install


@pytest.mark.anyio
async def test_чтение_разрешено(patched) -> None:
    """ГЛАВНОЕ. «Только чтение» обязано означать, что читать МОЖНО."""

    patched(False)
    with pytest.raises(_Called):
        await _middleware(False).dispatch(_request("GET", "/api/v1/persons"), _next)


@pytest.mark.anyio
async def test_запись_запрещена_и_причина_названа(patched) -> None:
    patched(False)
    response = await _middleware(False).dispatch(_request("POST", "/api/v1/persons"), _next)

    assert response.status_code == 409
    body = response.body.decode("utf-8")
    assert TENANT_SUSPENDED_READ_ONLY in body
    assert "приостановлена" in body
    # Клиент должен понять, что данные целы, — иначе решит, что их удалили.
    assert "сохранены" in body


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/login", "/api/v1/offboarding/request", "/api/v1/offboarding/export"],
)
async def test_вход_и_выгрузка_работают(patched, path: str) -> None:
    """Без этих исключений «только чтение» превращается в «нет доступа».

    Вход — POST; выгрузка и расторжение — тоже. Право забрать свои данные не
    зависит от того, оплачен ли следующий месяц.
    """

    patched(False)
    with pytest.raises(_Called):
        await _middleware(False).dispatch(_request("POST", path), _next)


@pytest.mark.anyio
async def test_действующий_арендатор_не_задет(patched) -> None:
    """Обратная сторона: правило не должно мешать тем, кто платит."""

    patched(True)
    with pytest.raises(_Called):
        await _middleware(True).dispatch(_request("POST", "/api/v1/persons"), _next)


@pytest.mark.anyio
async def test_неизвестный_арендатор_пропускается(patched) -> None:
    """Решает не этот слой: неизвестного арендатора отвергает разбор выше."""

    patched(None)
    with pytest.raises(_Called):
        await _middleware(None).dispatch(_request("POST", "/api/v1/persons"), _next)
