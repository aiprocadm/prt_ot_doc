"""Самостоятельная регистрация арендатора (BIZ-53 срез-3, Доп. №1 разд. 53.2).

ТЗ: «Регистрация и создание tenant — самостоятельно». До этого среза арендатор
мог появиться ТОЛЬКО через управляющий контур: ручка создания требует актора
платформы или reseller'а. То есть заказчик не мог начать сам — он должен был
кому-то написать, а ТЗ называет самостоятельный старт условием аренды.

## Три решения, без которых ручка была бы опасной

**1. Выключена по умолчанию.** Публичная ручка создаёт СХЕМУ в базе на каждый
успешный запрос из интернета. Включённая «вдруг, после обновления», она стала
бы и расходом, и вектором атаки. Владелец включает её сам, когда готов
принимать поток (``SELF_SERVICE_SIGNUP_ENABLED``). Выключенная отвечает 404, а
не 403: закрытая ручка не должна подтверждать, что она вообще существует.

**2. Свой счётчик попыток, строже общего.** Создание арендатора несопоставимо
дороже обычного запроса, поэтому у регистрации отдельный лимит по адресу
(``SELF_SERVICE_SIGNUP_PER_IP``, по умолчанию три в час), и считается он ДО
создания — перебор не стоит нам развёрнутых арендаторов.

**3. Тариф — стартовая редакция, а не «всё включено».** Самостоятельно
зарегистрировавшийся получает Start OT (разд. 53.1): дать по умолчанию полный
набор значило бы раздавать то, что продаётся.

## Что возвращается и почему именно так

Возвращаются слаг арендатора и e-mail владельца — то, чем он войдёт. Пароль
задаёт САМ регистрирующийся и в ответе не повторяется: эхо пароля попало бы в
журналы прокси и историю браузера. Подтверждения почты здесь нет намеренно: оно
требует настроенной доставки, а её на платформе может не быть — вводить
обязательный шаг, который у части установок не работает, значит сделать
регистрацию неработающей. Это названо границей среза, а не умолчано.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.anti_bot import AntiBotRefusal, resolve_config, verify_human, warn_if_unprotected
from app.core.config import get_settings
from app.core.external_perimeter import enforce_signup_attempts
from app.db.session import AsyncSessionLocal
from app.models.tenanting import Tenant
from app.modules.subscription.plans import DEFAULT_PLAN_CODE
from app.schemas.public_signup import SignupRequest, SignupResult
from app.services.tenants.bootstrap.service import BootstrapTenantService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])

#: Слаг арендатора — часть адреса и имя схемы в базе. Набор символов закрытый:
#: всё остальное ломало бы либо адрес, либо SQL-идентификатор.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")


def _signup_disabled() -> HTTPException:
    # 404, а не 403: выключенная ручка не подтверждает своё существование.
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


@router.post(
    "/public/signup",
    response_model=SignupResult,
    status_code=status.HTTP_201_CREATED,
    summary="Self-service tenant registration",
)
async def public_signup(payload: SignupRequest, request: Request) -> SignupResult:
    settings = get_settings()
    if not settings.self_service_signup_enabled:
        raise _signup_disabled()

    # Считаем попытку ДО создания: перебор не должен стоить нам арендаторов.
    enforce_signup_attempts(request, settings=settings)

    # SEC-68 (разд. 68.2): «человек ли это». Лимит по адресу не мешает боту с
    # набором адресов, а каждый успешный запрос создаёт СХЕМУ В БАЗЕ — это самая
    # дорогая кнопка, выставленная в интернет.
    #
    # Служба подключается НАСТРОЙКОЙ (правило продукта: внешняя зависимость —
    # настройка, а не разработка). Не подключена — регистрация работает на
    # прежних мерах, но об этом честно пишется предупреждение в журнал: молча
    # обходиться без проверки значило бы притворяться защищёнными.
    try:
        antibot = resolve_config(settings)
    except AntiBotRefusal as exc:
        # Настройка неполная: служба названа, секрета нет. Это ХУЖЕ отсутствия
        # настройки — владелец уверен, что защита включена. Поэтому отказ.
        logger.error("public_signup.antibot_misconfigured", extra={"reason": str(exc)})
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Registration is temporarily unavailable",
        ) from exc

    if antibot is None:
        warn_if_unprotected(settings)
    else:
        try:
            await verify_human(
                antibot,
                payload.antibot_token,
                remote_ip=request.client.host if request.client else None,
            )
        except AntiBotRefusal as exc:
            logger.warning("public_signup.antibot_rejected", extra={"reason": str(exc)})
            # Ответ ОДИНАКОВ для «нет ответа» и «ответ не принят»: разные
            # ответы подсказывали бы боту, где именно он ошибся.
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Anti-bot verification failed",
            ) from exc

    slug = payload.slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Slug must be 3–40 characters: lowercase letters, digits and dashes",
        )
    if slug == settings.managing_tenant_slug:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists")

    # Отдельная сессия без арендатора: строки пишутся ДРУГОМУ арендатору, как в
    # управляющем контуре провижининга.
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists")

        summary = await BootstrapTenantService(session).run(
            tenant_slug=slug,
            tenant_name=payload.company_name.strip(),
            owner_email=str(payload.owner_email).strip().lower(),
            owner_password=payload.owner_password,
            industry=payload.industry,
            # Стартовая редакция: полный набор продаётся, а не раздаётся.
            plan_code=DEFAULT_PLAN_CODE,
        )
        await session.commit()

    return SignupResult(
        tenant_slug=slug,
        owner_email=str(payload.owner_email).strip().lower(),
        plan_code=DEFAULT_PLAN_CODE,
        warnings=list(summary.warnings),
    )
