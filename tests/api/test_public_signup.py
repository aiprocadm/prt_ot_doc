"""BIZ-53 срез-3: самостоятельная регистрация арендатора (Доп. №1 разд. 53.2).

ТЗ: «Регистрация и создание tenant — самостоятельно». До этого среза арендатор
мог появиться ТОЛЬКО через управляющий контур — заказчик не мог начать сам.

Здесь закреплено то, без чего ручка была бы опасной:

* **по умолчанию она ВЫКЛЮЧЕНА** и отвечает 404 — включённая «вдруг, после
  обновления» публичная ручка создаёт схему в базе на каждый запрос из
  интернета;
* включённая — создаёт арендатора со СТАРТОВОЙ редакцией, а не «всё включено»;
* занятый слаг и слаг управляющего арендатора — 409, а не второй арендатор;
* пароль в ответе НЕ повторяется;
* попытки считаются по адресу, и счёт идёт ДО создания.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.tenanting import Tenant
from app.modules.subscription.plans import DEFAULT_PLAN_CODE

URL = "/api/v1/public/signup"


def _payload(slug: str = "novy-klient", **over) -> dict:
    body = {
        "slug": slug,
        "company_name": "ООО Новый клиент",
        "owner_email": f"owner@{slug}.example.com",
        "owner_password": "Secret123!",
    }
    body.update(over)
    return body


@pytest.fixture()
def signup_on(monkeypatch: pytest.MonkeyPatch):
    """Включить регистрацию так же, как это сделает владелец, — настройкой."""

    monkeypatch.setenv("SELF_SERVICE_SIGNUP_ENABLED", "true")
    # Лимит на время теста поднят: считается он по адресу, а тесты идут с одного.
    monkeypatch.setenv("SELF_SERVICE_SIGNUP_PER_IP", "100/hour")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from app.core import external_perimeter

    external_perimeter.reset_guard()
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]
    external_perimeter.reset_guard()


async def _tenant_exists(slug: str) -> bool:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        row = (
            await session.execute(select(Tenant.id).where(Tenant.slug == slug))
        ).scalar_one_or_none()
    return row is not None


@pytest.mark.anyio
async def test_по_умолчанию_регистрация_закрыта(async_client: AsyncClient) -> None:
    """404, а не 403: закрытая ручка не подтверждает своё существование.

    Это главная проверка среза. Публичная ручка создаёт СХЕМУ в базе на каждый
    успешный запрос — включённая по умолчанию, она стала бы и расходом, и
    вектором атаки на любой установке, которая просто обновилась.
    """

    get_settings.cache_clear()  # type: ignore[attr-defined]

    response = await async_client.post(URL, json=_payload("dolzhen-byt-zakryt"))

    assert response.status_code == 404, response.text
    assert not await _tenant_exists("dolzhen-byt-zakryt")


@pytest.mark.anyio
async def test_включённая_регистрация_создаёт_арендатора(
    async_client: AsyncClient, signup_on
) -> None:
    response = await async_client.post(URL, json=_payload("samostoyatelny"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tenant_slug"] == "samostoyatelny"
    assert body["owner_email"] == "owner@samostoyatelny.example.com"
    assert await _tenant_exists("samostoyatelny")


@pytest.mark.anyio
async def test_выдаётся_стартовая_редакция_а_не_всё_включено(
    async_client: AsyncClient, signup_on
) -> None:
    """Полный набор продаётся, а не раздаётся зарегистрировавшимся самим."""

    response = await async_client.post(URL, json=_payload("startovy-nabor"))

    assert response.status_code == 201, response.text
    assert response.json()["plan_code"] == DEFAULT_PLAN_CODE


@pytest.mark.anyio
async def test_пароль_в_ответе_не_повторяется(
    async_client: AsyncClient, signup_on
) -> None:
    """Эхо пароля попало бы в журналы прокси и историю браузера."""

    response = await async_client.post(URL, json=_payload("bez-eha"))

    assert response.status_code == 201, response.text
    assert "Secret123!" not in response.text


@pytest.mark.anyio
async def test_занятый_слаг_отклоняется(
    async_client: AsyncClient, signup_on
) -> None:
    first = await async_client.post(URL, json=_payload("zanyaty-slag"))
    assert first.status_code == 201, first.text

    second = await async_client.post(URL, json=_payload("zanyaty-slag"))

    assert second.status_code == 409, second.text


@pytest.mark.anyio
async def test_слаг_управляющего_арендатора_отклоняется(
    async_client: AsyncClient, signup_on
) -> None:
    """Иначе самостоятельная регистрация могла бы занять служебный контур."""

    managing = get_settings().managing_tenant_slug

    response = await async_client.post(URL, json=_payload(managing))

    assert response.status_code == 409, response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad", ["ab", "ЗАГЛАВНЫЕ", "с_подчёркиванием", "-начинается-с-дефиса", "точка.точка"]
)
async def test_негодный_слаг_отклоняется(
    async_client: AsyncClient, signup_on, bad: str
) -> None:
    """Слаг — часть адреса И имя схемы в базе: набор символов закрытый."""

    response = await async_client.post(URL, json=_payload(bad))

    assert response.status_code in (409, 422), response.text
    assert not await _tenant_exists(bad)


@pytest.mark.anyio
async def test_перебор_останавливается_лимитом(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Счёт идёт ДО создания — перебор не должен стоить нам арендаторов."""

    monkeypatch.setenv("SELF_SERVICE_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("SELF_SERVICE_SIGNUP_PER_IP", "1/hour")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from app.core import external_perimeter

    external_perimeter.reset_guard()
    try:
        first = await async_client.post(URL, json=_payload("limit-pervy"))
        assert first.status_code == 201, first.text

        second = await async_client.post(URL, json=_payload("limit-vtoroy"))

        assert second.status_code == 429, second.text
        assert not await _tenant_exists("limit-vtoroy")
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]
        external_perimeter.reset_guard()


@pytest.mark.anyio
async def test_бот_без_ответа_службы_не_создаёт_арендатора(
    async_client: AsyncClient, signup_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SEC-68 (разд. 68.2): когда служба проверки подключена, она обязательна.

    Лимит по адресу не мешает боту с сотней адресов — именно так делают
    регистрационный спам, а каждый успешный запрос создаёт СХЕМУ В БАЗЕ.
    """

    monkeypatch.setenv("SIGNUP_ANTIBOT_PROVIDER", "turnstile")
    monkeypatch.setenv("SIGNUP_ANTIBOT_SECRET", "s3cret")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    response = await async_client.post(URL, json=_payload("bot-ne-proydyot"))

    assert response.status_code == 400, response.text
    assert not await _tenant_exists("bot-ne-proydyot")


@pytest.mark.anyio
async def test_неполная_настройка_закрывает_регистрацию(
    async_client: AsyncClient, signup_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Служба названа, секрета нет — это ХУЖЕ, чем отсутствие настройки.

    Владелец в таком случае уверен, что защита включена, а её нет. Поэтому
    регистрация закрывается, а не работает «как будто всё в порядке».
    """

    monkeypatch.setenv("SIGNUP_ANTIBOT_PROVIDER", "turnstile")
    monkeypatch.delenv("SIGNUP_ANTIBOT_SECRET", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]

    response = await async_client.post(URL, json=_payload("nastroyka-nepolnaya"))

    assert response.status_code == 503, response.text
    assert not await _tenant_exists("nastroyka-nepolnaya")


@pytest.mark.anyio
async def test_без_подключённой_службы_регистрация_работает(
    async_client: AsyncClient, signup_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Обратная сторона: не подключено — не значит сломано.

    Без этой половины «починкой» можно было бы объявить запрет всем и сломать
    самостоятельный старт, который ТЗ называет условием аренды.
    """

    monkeypatch.delenv("SIGNUP_ANTIBOT_PROVIDER", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]

    response = await async_client.post(URL, json=_payload("bez-sluzhby-rabotaet"))

    assert response.status_code == 201, response.text
    assert await _tenant_exists("bez-sluzhby-rabotaet")

