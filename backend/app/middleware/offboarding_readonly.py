"""OPS-72 срез-4 (разд. 72.3): режим «только чтение» на время grace-периода.

ТЗ: «Grace-период: после расторжения данные хранятся N дней **(read-only)** на
случай возврата или споров». Срезы 2–3 сделали срок и удаление, но сам режим
чтения не был реализован: заявка на расторжение подана, а данные всё это время
продолжали меняться. Для периода, смысл которого — «зафиксировать состояние на
случай СПОРА», это дыра: спорить будут о данных, которые уже поехали.

Решения, которые важнее кода:

* **Проверка стоит на записи, а не на чтении.** Read-only означает «читать
  можно», поэтому GET/HEAD/OPTIONS не платят ни одного лишнего запроса к базе.
  Запрос статуса офбординга делается только для изменяющих методов.
* **Два исключения, и оба обязательны.** ``/auth`` — иначе клиент не сможет
  войти, чтобы забрать данные (логин это POST), а «read-only» превратится в
  «недоступно». ``/offboarding`` — иначе нельзя ни ОТМЕНИТЬ расторжение
  (клиент вернулся), ни запустить удаление: режим запер бы сам выход из себя.
* **Отказ говорит, до какой даты действует режим.** «Запрещено» без даты
  окончания читается как поломка и порождает обращение в поддержку; с датой —
  это понятное состояние, у которого есть кнопка «отменить расторжение».
* **Статус читается из БД на каждый пишущий запрос, без кэша.** Кэш дал бы
  окно, в котором отменивший расторжение клиент всё ещё не может работать —
  ровно в тот момент, когда он вернулся и ждёт, что всё заработает.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.dependencies import _fetch_tenant_by_identifier, _resolve_tenant_slug
from app.db.session import AsyncSessionLocal
from app.models.offboarding import TenantOffboarding

__all__ = ["OffboardingReadOnlyMiddleware", "READ_ONLY_ERROR_CODE"]

READ_ONLY_ERROR_CODE = "TENANT_OFFBOARDING_READ_ONLY"

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Пути, которые обязаны работать и в режиме только чтения.
_ALWAYS_WRITABLE_PREFIXES = (
    # Вход в систему — POST. Без него «только чтение» стало бы «нет доступа», и
    # клиент не смог бы забрать собственные данные.
    "/api/v1/auth",
    # Отмена расторжения, экспорт и само удаление. Режим не должен запирать
    # выход из себя.
    "/api/v1/offboarding",
)


class OffboardingReadOnlyMiddleware(BaseHTTPMiddleware):
    """Запретить запись арендатору, находящемуся в grace-периоде офбординга."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method.upper() not in _MUTATING_METHODS
            or not path.startswith("/api/v1")
            or path.startswith(_ALWAYS_WRITABLE_PREFIXES)
        ):
            return await call_next(request)

        tenant_slug = _resolve_tenant_slug(request)
        if not tenant_slug:
            return await call_next(request)

        grace_until = await self._active_grace_until(tenant_slug)
        if grace_until is None:
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": {
                    "code": READ_ONLY_ERROR_CODE,
                    "type": "offboarding",
                    "message": (
                        "Арендатор в процессе расторжения: данные доступны только "
                        f"на чтение до {grace_until.isoformat()}. "
                        "Чтобы продолжить работу, отмените расторжение."
                    ),
                    "grace_until": grace_until.isoformat(),
                }
            },
        )

    @staticmethod
    async def _active_grace_until(tenant_identifier: str) -> datetime | None:
        """Дата окончания активного grace-периода или ``None``.

        Арендатор ищется тем же способом, что и во всём приложении
        (``_fetch_tenant_by_identifier``): в заголовке ``X-Tenant`` может стоять
        и slug, и код, и UUID. Собственный поиск «только по slug» тихо не нашёл
        бы арендатора при UUID-заголовке и пропустил бы запись — отказ защиты,
        выглядящий как разрешение.

        Сессия под строку офбординга пиннится на арендатора: под FORCE RLS
        (SEC-65) tenant-less сессия не увидела бы её вовсе — тот же тихий провал.
        """

        try:
            tenant = await _fetch_tenant_by_identifier(tenant_identifier)
        except HTTPException:
            # Неизвестный или неактивный арендатор — не наша забота: пусть
            # обычный обработчик вернёт свой 404/403, а не наш 409.
            return None

        async with AsyncSessionLocal(
            tenant=tenant.slug, include_public=False, create_schema=False
        ) as session:
            record = (
                (
                    await session.execute(
                        select(TenantOffboarding)
                        .where(
                            TenantOffboarding.tenant_id == str(tenant.id),
                            TenantOffboarding.status == "grace",
                        )
                        .order_by(TenantOffboarding.requested_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if record is None:
                return None
            grace_until = record.grace_until
            if grace_until.tzinfo is None:
                grace_until = grace_until.replace(tzinfo=timezone.utc)
            # Истёкший grace режим НЕ снимает: данные ждут удаления, и менять их
            # тем более незачем. Снять режим может только отмена расторжения —
            # то есть решение человека, а не наступление даты.
            return grace_until
