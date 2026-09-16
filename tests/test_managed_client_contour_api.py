"""BIZ-49 (разд. 49.3): вход специалиста В КОНТУР Dedicated-клиента.

ЗАЧЕМ. Портфель умел ЧИТАТЬ контур Dedicated-клиента для сводки, но человек
внутрь контура войти не мог: строки ``User`` живут в схеме арендатора, и
личности у специалиста аутсорсера там не было. Отсюда «вошёл в контекст, а
данных нет» — ровно то, что честно значилось остатком строки BIZ-49.

Здесь проверяется МЕСТО ПОДКЛЮЧЕНИЯ, а не только правила: ручка входа в
контекст действительно выдаёт ключ от контура, выход его действительно гасит,
а запреты разд. 63.2 действуют и там, где заголовка «работаю от имени» нет.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.api.routes import auth as auth_routes
from app.api.routes import managed_clients as routes
from app.core.security import decode_token, issue_access_token
from app.domains.managed_clients.delegated_identity import (
    DELEGATED_CLIENT_CLAIM,
    DELEGATED_FROM_CLAIM,
    delegated_email,
)
from app.domains.managed_clients.delegation import NO_CONSENT_REASON, NOT_A_CHILD_REASON
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.middleware.impersonation_guard import (
    IMPERSONATION_FORBIDDEN_CODE,
    ImpersonationGuardMiddleware,
)
from app.models.identity import User
from app.models.managed_clients import (
    ManagedClient,
    ManagedClientAccess,
    ManagedClientConsent,
)
from app.models.models import Tenant
from app.models.tenant_billing import RoleEnum
from app.services import managed_client_contour as contour_service
from app.services.auth import hash_password

_SLUG = "test"
_CLIENT_SLUG = "romashka-contour"
_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def _tenant(tid):
    return SimpleNamespace(id=tid, is_active=True, slug=_SLUG, code=_SLUG, name="Аутсорсер")


def _auth(sub="spec-1"):
    return SimpleNamespace(sub=sub, tenant_id=None, roles=["ot_specialist"], company_id=None)


def _request(path="/api/v1/persons", method="GET"):
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
        url=SimpleNamespace(path=path),
        method=method,
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))


@pytest.fixture()
def identity_calls(monkeypatch):
    """Подменяем ЗАПИСЬ в чужой контур, оставляя всё решение настоящим.

    Граница названа честно: право на вход, вердикт делегирования и сам ключ
    считаются здесь по-настоящему; в тестовой базе нет второй схемы, поэтому
    заведение строки пользователя в ней записывается, а не выполняется.
    """

    calls: dict[str, list] = {"ensure": [], "extinguish": []}

    async def _ensure(**kwargs):
        calls["ensure"].append(kwargs)
        return "identity-1", RoleEnum.OT_SPECIALIST.value

    async def _extinguish(**kwargs):
        calls["extinguish"].append(kwargs)
        return True

    monkeypatch.setattr(contour_service, "ensure_contour_identity", _ensure)
    monkeypatch.setattr(contour_service, "extinguish_contour_identity", _extinguish)
    return calls


async def _tenant_id(session) -> str:
    return (await session.execute(select(Tenant).where(Tenant.slug == _SLUG))).scalars().one().id


async def _dedicated_client(
    session,
    tid,
    *,
    user_id="spec-1",
    with_consent=True,
    child=True,
    slug=_CLIENT_SLUG,
):
    """Dedicated-клиент со своим контуром, грантом и (обычно) согласием."""

    client_tenant = Tenant(
        slug=slug,
        name="ООО Ромашка",
        code=slug,
        contact_email=f"admin@{slug}.ru",
        is_active=True,
        parent_id=tid if child else None,
    )
    session.add(client_tenant)
    session.add(
        User(
            tenant_id=tid,
            email="spec@acme.ru",
            full_name="Иванов И.",
            role=RoleEnum.OT_SPECIALIST,
            hashed_password="$argon2id$fake",
            is_active=True,
            id=user_id,
        )
    )
    client = ManagedClient(
        tenant_id=tid,
        name="ООО Ромашка",
        mode=ManagedClientMode.DEDICATED,
        dedicated_tenant_slug=slug,
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(client)
    await session.flush()
    session.add(
        ManagedClientAccess(
            tenant_id=tid,
            managed_client_id=client.id,
            user_id=user_id,
            all_modules=True,
            modules=[],
            granted_at=_NOW,
        )
    )
    if with_consent:
        session.add(
            ManagedClientConsent(
                tenant_id=tid,
                managed_client_id=client.id,
                document_ref="Поручение №1",
                granted_at=_NOW,
                granted_by_user_id="admin-1",
            )
        )
    await session.flush()
    return client


async def _enter(session, tid, client_id):
    return await routes.enter_client_context(
        mcid=client_id,
        request=_request(),
        tenant=_tenant(tid),
        session=session,
        access=SimpleNamespace(),
        auth=_auth(),
    )


@pytest.mark.asyncio
async def test_вход_в_контекст_выдаёт_ключ_от_контура(sessionmaker, identity_calls):
    """ГЛАВНОЕ. У Dedicated-клиента вход в контекст обязан дать ключ ОТ КОНТУРА.

    Без него специалист «вошёл от имени клиента», а данных не видит: они лежат
    в другом арендаторе. Именно это и значилось остатком строки BIZ-49.
    """

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid)

        out = await _enter(session, tid, client.id)

    assert out.contour is not None, "вход без ключа от контура оставляет специалиста ни с чем"
    assert out.contour.tenant_slug == _CLIENT_SLUG
    assert out.contour_reason is None
    assert identity_calls["ensure"], "личность в контуре клиента не заводилась"


@pytest.mark.asyncio
async def test_ключ_выписан_к_контуру_клиента_и_помечен(sessionmaker, identity_calls):
    """Токен обязан САМ говорить, к чьему контуру он и что он делегированный.

    Метку нельзя заменить заголовком: заголовок можно не прислать, и запреты
    разд. 63.2 обошлись бы молча.
    """

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid)

        out = await _enter(session, tid, client.id)

    payload = decode_token(out.contour.access_token)

    assert payload["tenant"] == _CLIENT_SLUG
    assert payload[DELEGATED_CLIENT_CLAIM] == client.id
    assert payload[DELEGATED_FROM_CLAIM] == _SLUG
    assert payload["sub"] == "identity-1"


@pytest.mark.asyncio
async def test_без_согласия_в_контур_не_попасть(sessionmaker, identity_calls):
    """Без действующего согласия клиента вход отвергается ЦЕЛИКОМ.

    Согласие — основание обработки, и проверяется оно раньше контура: до
    выдачи ключа дело не доходит вовсе. Личность при этом не заводится — иначе
    в контуре клиента осталась бы учётка, заведённая без основания.
    """

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid, with_consent=False, slug="no-consent-co")

        with pytest.raises(HTTPException) as exc:
            await _enter(session, tid, client.id)

    assert exc.value.status_code == 409
    assert not identity_calls["ensure"], "личность завели без основания"


@pytest.mark.asyncio
async def test_служба_входа_сама_отказывает_без_согласия(sessionmaker, identity_calls):
    """Второй рубеж: служба входа НЕ полагается на проверку выше по течению.

    Ручка сегодня проверяет согласие первой, но службу вызовут и из другого
    места; тогда единственная проверка окажется не пройденной.
    """

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid, with_consent=False, slug="direct-call-co")

        entry, reason = await contour_service.open_contour_session(
            session,
            client=client,
            outsourcer_tenant=_tenant(tid),
            specialist_user_id="spec-1",
            now=_NOW,
        )

    assert entry is None
    assert reason == NO_CONSENT_REASON
    assert not identity_calls["ensure"]


@pytest.mark.asyncio
async def test_чужой_контур_не_открывается_даже_если_слаг_вписан(sessionmaker, identity_calls):
    """Контур, не заведённый ПОД этим аутсорсером, — чужой.

    Иначе достаточно было бы вписать в карточку любой слаг, и платформа сама
    выписала бы ключ от чужого арендатора.
    """

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid, child=False, slug="strangers-co")

        out = await _enter(session, tid, client.id)

    assert out.contour is None
    assert out.contour_reason == NOT_A_CHILD_REASON
    assert not identity_calls["ensure"]


@pytest.mark.asyncio
async def test_выход_гасит_личность_в_контуре(sessionmaker, identity_calls):
    """Выход обязан гасить личность: иначе ключ работает после выхода."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid, slug="leaving-co")
        await _enter(session, tid, client.id)

        await routes.leave_client_context(
            request=_request(),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )

    assert identity_calls["extinguish"], "после выхода личность осталась живой"
    assert identity_calls["extinguish"][0]["specialist_user_id"] == "spec-1"


@pytest.mark.asyncio
async def test_снятый_грант_гасит_личность(sessionmaker, identity_calls):
    """Отключили специалиста — ключ от чужого контура не должен пережить это."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _dedicated_client(session, tid, slug="revoked-co")
        await _enter(session, tid, client.id)
        grant = (
            (
                await session.execute(
                    select(ManagedClientAccess).where(
                        ManagedClientAccess.managed_client_id == client.id
                    )
                )
            )
            .scalars()
            .one()
        )

        await routes.revoke_access(
            mcid=client.id,
            grant_id=grant.id,
            request=_request(),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            auth=_auth("admin-1"),
        )

    assert identity_calls["extinguish"], "снятый грант оставил личность в контуре живой"


# --- Запреты разд. 63.2 в чужом контуре ---


class _Passed(Exception):
    """Запрос прошёл дальше — сторож не вмешался."""


async def _next(_request):
    raise _Passed


def _http_request(method: str, path: str, token: str | None) -> SimpleNamespace:
    headers = {}
    if token:
        headers["authorization"] = f"Bearer {token}"
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers=headers,
    )


def _contour_token() -> str:
    return issue_access_token(
        subject="identity-1",
        tenant=_CLIENT_SLUG,
        role=RoleEnum.OT_SPECIALIST.value,
        additional_claims={DELEGATED_CLIENT_CLAIM: "mc-1", DELEGATED_FROM_CLAIM: _SLUG},
    )


def _ordinary_token() -> str:
    return issue_access_token(subject="u-1", tenant=_SLUG, role=RoleEnum.OT_SPECIALIST.value)


@pytest.mark.anyio
async def test_запреты_действуют_и_в_контуре_клиента() -> None:
    """ГЛАВНОЕ ПО БЕЗОПАСНОСТИ. В контуре клиента заголовка «от имени» НЕТ.

    Пока сторож смотрел только на заголовок, вход в контур был заодно обходом
    всех запретов разд. 63.2 — платёжные данные, ключи доступа, удаление.
    """

    middleware = ImpersonationGuardMiddleware(app=None)  # type: ignore[arg-type]

    response = await middleware.dispatch(
        _http_request("POST", "/api/v1/api-tokens", _contour_token()), _next
    )

    assert response.status_code == 403
    assert IMPERSONATION_FORBIDDEN_CODE in response.body.decode("utf-8")


@pytest.mark.anyio
async def test_обычная_работа_под_своей_ролью_не_задета() -> None:
    """Обратная сторона: сторож не должен мешать тем, кто работает у себя."""

    middleware = ImpersonationGuardMiddleware(app=None)  # type: ignore[arg-type]

    with pytest.raises(_Passed):
        await middleware.dispatch(
            _http_request("POST", "/api/v1/api-tokens", _ordinary_token()), _next
        )


@pytest.mark.anyio
async def test_безопасный_путь_не_разбирает_токен() -> None:
    """Опасных путей единицы: обычный запрос не должен платить за сторожа."""

    middleware = ImpersonationGuardMiddleware(app=None)  # type: ignore[arg-type]

    with pytest.raises(_Passed):
        await middleware.dispatch(_http_request("GET", "/api/v1/persons", _contour_token()), _next)


# --- У личности нет второго входа ---


def _http_login_request():
    """Настоящий Request: ограничитель частоты не работает с подделкой."""

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"user-agent", b"tests")],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
async def test_личность_не_войдёт_даже_с_верным_паролем(sessionmaker) -> None:
    """ГЛАВНОЕ. Был бы у личности пароль — был бы и ВТОРОЙ вход в контур клиента.

    Он пережил бы и отзыв гранта, и отзыв согласия, и выглядел бы в журнале
    как обычный вход сотрудника клиента. Поэтому проверка стоит ЯВНО, а не
    держится на том, что метка не сойдётся с хэшем: здесь пароль подобран
    ВЕРНО, и без явной проверки вход бы состоялся.
    """

    email = delegated_email(specialist_user_id="spec-9", outsourcer_slug="acme")
    async with sessionmaker() as session:
        tenant_row = (
            (await session.execute(select(Tenant).where(Tenant.slug == _SLUG))).scalars().one()
        )
        session.add(
            User(
                tenant_id=tenant_row.id,
                email=email,
                full_name="Иванов И. (аутсорсер «Ромашка»)",
                role=RoleEnum.OT_SPECIALIST,
                hashed_password=hash_password("Whatever123"),
                is_active=True,
            )
        )
        await session.flush()

        with pytest.raises(HTTPException) as exc:
            await auth_routes.login(
                request=_http_login_request(),
                response=SimpleNamespace(headers={}),
                payload=SimpleNamespace(email=email, password="Whatever123"),
                session=session,
                tenant=tenant_row,
            )

    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_адрес_личности_не_принимает_даже_форма_входа(async_client) -> None:
    """Третий рубеж, доставшийся даром от выбора домена ``.invalid``.

    Разбор адреса отвергает зарезервированный домен ещё до обработчика: такой
    адрес нельзя даже отправить в форму входа.
    """

    response = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": delegated_email(specialist_user_id="spec-9", outsourcer_slug="acme"),
            "password": "Whatever123",
        },
        headers={"x-tenant": "test"},
    )

    assert response.status_code == 422, response.text
