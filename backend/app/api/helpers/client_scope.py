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
from sqlalchemy import false as sa_false
from sqlalchemy import select

from app.core.errors import api_problem_detail
from app.domains.managed_clients.scope import ClientDataScope
from app.models.models import Person

__all__ = [
    "IMPERSONATION_FORBIDDEN_CODE",
    "apply_company_scope",
    "apply_person_scope",
    "SCOPE_NOT_FOUND_CODE",
    "SCOPE_WRITE_DENIED_CODE",
    "ensure_in_client_scope",
    "ensure_person_in_client_scope",
    "filter_rows_by_person_scope",
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


def apply_person_scope(stmt, column, scope: ClientDataScope | None, *, tenant_id: str):
    """Сузить выборку до записей, привязанных к СОТРУДНИКАМ клиента.

    Так устроены медосмотры, выдачи СИЗ и записи на обучение: своей
    организации у них нет, принадлежность клиенту идёт через человека.

    Подзапросом, а не join'ом: пагинация и подсчёт итога идут по той же
    выборке, а join размножил бы строки.
    """

    if scope is None:
        return stmt
    if not scope.visible:
        # Пусто, а не «все записи арендатора»: см. правила fail-closed.
        return stmt.where(sa_false())
    return stmt.where(
        column.in_(
            select(Person.id).where(
                Person.tenant_id == tenant_id,
                Person.company_id == scope.company_id,
                Person.deleted_at.is_(None),
            )
        )
    )


def apply_company_scope(stmt, column, scope: ClientDataScope | None):
    """Сузить выборку до записей самой организации клиента (документы, люди)."""

    if scope is None:
        return stmt
    if not scope.visible:
        return stmt.where(sa_false())
    return stmt.where(column == scope.company_id)


async def ensure_person_in_client_scope(
    session, person_id: str | None, scope: ClientDataScope | None, *, tenant_id: str
) -> None:
    """Проверить принадлежность записи клиенту ЧЕРЕЗ сотрудника.

    Для медосмотров, СИЗ и обучения своей организации у записи нет. Отдельный
    запрос делается только в контексте клиента: обычная работа не должна
    платить лишним обращением к базе на каждую карточку.
    """

    if scope is None:
        return
    if not scope.visible or not person_id:
        raise _not_found("Record")
    company_id = await session.scalar(
        select(Person.company_id).where(
            Person.id == person_id,
            Person.tenant_id == tenant_id,
            Person.deleted_at.is_(None),
        )
    )
    ensure_in_client_scope(scope, company_id, entity="Record")


async def filter_rows_by_person_scope(
    session, rows: list, person_id_of, scope: ClientDataScope | None, *, tenant_id: str
) -> list:
    """Отфильтровать УЖЕ полученные строки по сотрудникам клиента.

    Нужно там, где выборку строит модуль, которому нечего знать про ведомых
    клиентов (ARCH-3): вместо протаскивания чужого понятия внутрь модуля
    отбираем на границе.
    """

    if scope is None:
        return rows
    if not scope.visible:
        return []
    ids = set(
        (
            await session.execute(
                select(Person.id).where(
                    Person.tenant_id == tenant_id,
                    Person.company_id == scope.company_id,
                    Person.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return [row for row in rows if person_id_of(row) in ids]
