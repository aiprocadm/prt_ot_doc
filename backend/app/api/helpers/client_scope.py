"""BIZ-49 срез-9: применение контекста клиента к выборкам и записи.

Один помощник на все роуты, которые умеют работать «от имени клиента»
(разд. 49.3). Держим правила в одном месте, потому что расходиться им нельзя:
раздел, где «чужой» ответил 404, а соседний — 403, сам рассказывает, что
запись существует.

Два решения:

* **Чужая строка — 404, а не 403.** «Доступ запрещён» подтверждает, что такой
  человек у аутсорсера есть. В контексте клиента это уже утечка: специалист
  подбором идентификаторов узнаёт состав чужой организации.
* **Запись при невидимой области — отказ с объяснением, а не тихий проброс.**
  Если данные клиента лежат в другом контуре, «сохранить» ушло бы в данные
  аутсорсера. Лучше честное «в этом контексте писать некуда» с причиной.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.errors import api_problem_detail
from app.domains.managed_clients.scope import ClientDataScope

__all__ = [
    "IMPERSONATION_FORBIDDEN_CODE",
    "SCOPE_NOT_FOUND_CODE",
    "SCOPE_WRITE_DENIED_CODE",
    "ensure_in_client_scope",
    "ensure_writable_client_scope",
    "forbid_impersonated_action",
    "scope_company_id",
]

SCOPE_NOT_FOUND_CODE = "NOT_FOUND"
SCOPE_WRITE_DENIED_CODE = "MANAGED_CLIENT_SCOPE_WRITE_DENIED"
IMPERSONATION_FORBIDDEN_CODE = "MANAGED_CLIENT_ACTION_FORBIDDEN"


def scope_company_id(scope: ClientDataScope | None) -> str | None:
    """Организация, которой ограничена выборка. ``None`` — ограничения нет."""

    return scope.company_id if scope is not None else None


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{entity} not found")


def ensure_in_client_scope(
    scope: ClientDataScope | None, company_id: str | None, *, entity: str
) -> None:
    """Проверить, что запись принадлежит клиенту, от имени которого работают."""

    if scope is None:
        return
    if not scope.visible or str(company_id or "") != str(scope.company_id):
        raise _not_found(entity)


def forbid_impersonated_action(scope: ClientDataScope | None, *, action: str) -> None:
    """Действие, запрещённое в контексте клиента (Доп. №3, разд. 63.2).

    Работа «от имени» даёт легальный доступ к чужим данным, и ровно поэтому
    часть действий из-под неё запрещена целиком — удаление данных, смена
    паролей и настроек безопасности. Отказ говорит, что делать: выйти из
    контекста и повторить под своей ролью, если право есть.
    """

    if scope is None:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(
            code=IMPERSONATION_FORBIDDEN_CODE,
            message=(
                f"Действие «{action}» запрещено в контексте клиента "
                f"«{scope.client_name}». Выйдите из контекста и повторите."
            ),
            error_type="managed_clients",
        ),
    )


def ensure_writable_client_scope(scope: ClientDataScope | None) -> None:
    """Запретить запись, когда данных клиента в этом контуре не существует."""

    if scope is None or scope.visible:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code=SCOPE_WRITE_DENIED_CODE,
            message=(f"Нельзя писать данные от имени «{scope.client_name}». " f"{scope.reason}"),
            error_type="managed_clients",
        ),
    )
